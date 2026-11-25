"""Run the historical baselines on the frozen common queries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime
import json
from pathlib import Path
import socket
import subprocess
import sys

from baselines.esti.build import BUILD as ESTI_CACHE, build as build_esti
from radius.run import ROOT, WORKLOADS, compile_tool, digest, read_rows


def read_json(path):
    return json.loads(path.read_text())


def launch(script, *args, log, check=True):
    return subprocess.run([sys.executable, ROOT / "src" / script, *map(str, args)],
                          cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=check)


def run_graph(graph, spec, output, search):
    work = WORKLOADS / graph
    queries = work / "test.tsv"
    edges = ROOT / "dataset/prepared" / f"{graph}.edges"
    target = output / graph
    target.mkdir()
    with (target / "run.log").open("w") as log:
        if not edges.exists():
            launch("prepare.py" if graph in ("wiki-Vote", "p2p-Gnutella31") else "freeze.py",
                   graph, log=log)
        manifest = read_json(work / "manifest.json")
        test = manifest["splits"]["test"]
        nodes = spec["nodes"]
        if nodes != manifest["nodes"] or digest(edges) != manifest["graph_sha256"] or digest(queries) != test["sha256"]:
            raise ValueError(f"{graph}: graph or query differs from the frozen input")
        with (target / "search.tsv").open("w") as data:
            subprocess.run([search, str(nodes), edges, queries], stdout=data, stderr=log, check=True)
        launch("baselines/historical.py", "--graph", graph, "--nodes", nodes, "--edges", spec["edges"],
               "--output", target / "historical.json", log=log)
        large = nodes >= 100_000
        launch("baselines/scalable/run.py", "--graph", edges, "--nodes", nodes, "--queries", queries,
               "--b", 16 if large else 1000, "--d2-cap", 4 if large else 32,
               "--output", target / "scalable.json", log=log, check=False)
        launch("baselines/cover/matrix.py", graph, "--timeout", 180, "--memory-mib", 4096,
               "--output", output / "labels", log=log)
    print(f"{graph}: receipts at {target}", flush=True)


def review(graph, output):
    target = output / graph
    historical = read_json(target / "historical.json")
    scalable = read_json(target / "scalable.json")
    frozen = read_json(WORKLOADS / graph / "manifest.json")
    test = frozen["splits"]["test"]
    n = test["queries"]
    k_counts = {}
    for query in read_rows(WORKLOADS / graph / "test.tsv"):
        k = int(query["k"])
        k_counts[k] = k_counts.get(k, 0) + 1
    if sorted(k_counts) != [2, 4, 6]:
        raise ValueError(f"{graph}: expected k=2,4,6")
    if (historical["test_sha256"], scalable["workload_sha256"]) != (test["sha256"],) * 2:
        raise ValueError(f"{graph}: query receipt mismatch")
    if (historical["graph_sha256"], scalable["graph_sha256"]) != (frozen["graph_sha256"],) * 2:
        raise ValueError(f"{graph}: graph receipt mismatch")

    rows = []

    def record(method, status, expected, checked=None, errors=None):
        if status in ("ok", "passed", "verified"):
            status = "verified" if checked == expected and errors == 0 else "invalid"
        rows.append(dict(graph=graph, method=method, status=status, expected=expected,
                         checked=checked, mismatches=errors))

    for row in read_rows(target / "search.tsv"):
        errors = int(row["mismatches"])
        record(row["method"], "mismatch" if errors else "verified", n, int(row["queries"]), errors)
    for row in historical["kreach"]:
        status = "allocation_failed" if "bad_alloc" in row.get("detail", "") else row["status"]
        record(f"kreach-{row['k']}", status, k_counts[row["k"]], row.get("queries"), row.get("mismatches"))
    for method in ("esti", "esti_expanded"):
        if method in historical:
            row = historical[method]
            record(method, row["status"], n, row.get("queries"), row.get("mismatches"))
    for row in scalable["runs"]:
        mode = row["mode"]
        record("gen-k-reach" if mode == "general" else f"scalable-{mode}", row["status"],
               n if mode == "general" else k_counts[int(mode)], row.get("n_queries"), row.get("errors"))
    for method in ("vcrea", "vcrea-plus", "pll"):
        receipt = read_json(output / "labels" / graph / f"{method}.json")
        if (receipt["edges_sha256"], receipt["queries_sha256"]) != (frozen["graph_sha256"], test["sha256"]):
            raise ValueError(f"{graph}: {method} receipt mismatch")
        row = receipt["results"][0]
        classes = row.get("by_class")
        record(method, row["status"], n, sum(c["n"] for c in classes.values()) if classes else None,
               sum(c["mismatches"] for c in classes.values()) if classes else None)
    expected = {"bfs", "bibfs", "esti", "gen-k-reach", "vcrea", "vcrea-plus", "pll"}
    expected |= {f"{method}-{k}" for method in ("kreach", "scalable") for k in k_counts}
    if historical["esti"]["status"] == "exceeds_upstream_capacity":
        expected.add("esti_expanded")
    if len(rows) != len(expected) or {row["method"] for row in rows} != expected:
        raise ValueError(f"{graph}: incomplete baseline matrix")
    return rows


def write_coverage(output, selected):
    rows = [row for name in selected for row in review(name, output)]
    with (output / "coverage.tsv").open("w") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} baseline configurations recorded in {output / 'coverage.tsv'}")
    valid = {"verified", "timeout", "time_limit", "allocation_failed", "exceeds_upstream_capacity"}
    if any(row["status"] not in valid for row in rows):
        raise SystemExit("Inspect the failed configurations in coverage.tsv")


def main():
    graphs = read_json(ROOT / "dataset/manifest.json") | read_json(ROOT / "dataset/catalogue.json")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graphs", nargs="*", metavar="GRAPH",
                        help="graph names or all")
    parser.add_argument("--review", type=Path, help="check and rebuild coverage.tsv from an existing run")
    parser.add_argument("--output", type=Path, help="new run directory under output/baselines/")
    parser.add_argument("--jobs", type=int, default=1, help="parallel graphs; each solver is single-threaded")
    args = parser.parse_args()
    if args.review:
        if args.graphs or args.output:
            parser.error("--review expects only an existing run directory")
        recorded = read_json(args.review / "run.json")["graphs"]
        write_coverage(args.review, recorded)
        return
    if not args.graphs or set(args.graphs) - (graphs.keys() | {"all"}):
        parser.error("choose all or one of " + ", ".join(sorted(graphs)))
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    selected = (sorted(graphs, key=lambda name: (-graphs[name]["edges"], name))
                if "all" in args.graphs else list(dict.fromkeys(args.graphs)))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = (args.output or ROOT / "output/baselines" / stamp).resolve()
    output.mkdir(parents=True, exist_ok=False)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    compiler = subprocess.check_output(["g++", "-dumpfullversion"], text=True).strip()
    (output / "run.json").write_text(json.dumps(dict(graphs=selected, timestamp=stamp, host=socket.gethostname(),
                                                    jobs=args.jobs, git_revision=revision, compiler=compiler),
                                                indent=2) + "\n")
    if not (ESTI_CACHE / "esti").exists():
        build_esti()
    search = compile_tool("search")
    with ThreadPoolExecutor(max_workers=args.jobs) as jobs:
        futures = [jobs.submit(run_graph, name, graphs[name], output, search) for name in selected]
        for future in futures:
            future.result()
    write_coverage(output, selected)


if __name__ == "__main__":
    main()
