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


def input_for(graph, spec, query_name):
    work = WORKLOADS / graph
    queries = work / query_name
    edges = ROOT / "dataset/prepared" / f"{graph}.edges"
    manifest = read_json(work / "manifest.json" if query_name == "test.tsv" else queries.with_suffix(".json"))
    test = manifest["splits"][queries.stem]
    if spec["nodes"] != manifest["nodes"] or digest(edges) != manifest["graph_sha256"] or digest(queries) != test["sha256"]:
        raise ValueError(f"{graph}: graph or query differs from frozen input")
    return work, edges, queries


FAMILIES = ("search", "esti", "scalable", "labels", "kreach")


def run_family(graph, spec, family, output, search, args):
    target = output / graph
    target.mkdir(exist_ok=True)
    _, edges, queries = input_for(graph, spec, args.query_name)
    nodes = spec["nodes"]
    with (target / f"{family}.log").open("a") as log:
        if family == "search":
            result = target / "search.tsv"
            if result.exists() and len(read_rows(result)) == 2:
                return
            with result.open("w") as data:
                subprocess.run([search, str(nodes), edges, queries], stdout=data, stderr=log, check=True)
        elif family == "scalable":
            result = target / "scalable.json"
            if result.exists() and len(read_json(result)["runs"]) == 4:
                return
            launch("baselines/scalable/run.py", "--graph", edges, "--nodes", nodes, "--queries", queries,
                   "--b", args.b, "--d2-cap", args.d2_cap, "--memory-gib", args.memory_gib,
                   "--output", result, log=log, check=False)
        elif family == "labels":
            launch("baselines/cover/matrix.py", graph, "--memory-mib", args.memory_gib*1024,
                   "--query-name", args.query_name, "--output", output / "labels", log=log)
        else:
            result = target / f"{family}.json"
            if result.exists():
                prior = read_json(result)
                if (family == "esti" and ("esti_expanded" in prior or prior.get("esti",{}).get("status")=="passed")
                    or family == "kreach" and len(prior["kreach"])==3):
                    return
            launch("baselines/historical.py", "--graph", graph, "--nodes", nodes, "--edges", spec["edges"],
                   "--memory-gib", args.kreach_memory_gib if family=="kreach" else args.memory_gib,
                   "--query-name", args.query_name, "--methods", family,
                   "--output", result, "--resume", log=log)
    print(f"{graph}: {family} complete", flush=True)


def review(graph, output, query_name="test.tsv"):
    target = output / graph
    combined = target / "historical.json"
    receipts = [read_json(combined)] if combined.exists() else [
        read_json(target / "esti.json"), read_json(target / "kreach.json")]
    historical = receipts[0].copy()
    for receipt in receipts[1:]:
        historical.update(receipt)
    scalable = read_json(target / "scalable.json")
    queries = WORKLOADS / graph / query_name
    frozen = read_json(queries.parent / "manifest.json" if query_name=="test.tsv" else queries.with_suffix(".json"))
    test = frozen["splits"][queries.stem]
    n = test["queries"]
    k_counts = {}
    for query in read_rows(queries):
        k = int(query["k"])
        k_counts[k] = k_counts.get(k, 0) + 1
    if sorted(k_counts) != [2, 4, 6]:
        raise ValueError(f"{graph}: expected k=2,4,6")
    if any(r["test_sha256"] != test["sha256"] for r in receipts) or scalable["workload_sha256"] != test["sha256"]:
        raise ValueError(f"{graph}: query receipt mismatch")
    if any(r["graph_sha256"] != frozen["graph_sha256"] for r in receipts) or scalable["graph_sha256"] != frozen["graph_sha256"]:
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


def write_coverage(output, selected, query_name="test.tsv"):
    rows = [row for name in selected for row in review(name, output, query_name)]
    with (output / "coverage.tsv").open("w") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} baseline configurations recorded in {output / 'coverage.tsv'}")
    valid = {"verified", "timeout", "time_limit", "allocation_failed", "exceeds_upstream_capacity"}
    if any(row["status"] not in valid for row in rows):
        raise SystemExit("Inspect the failed configurations in coverage.tsv")


def main():
    synthetic = read_json(ROOT / "dataset/synthetic.json")
    graphs = read_json(ROOT / "dataset/manifest.json") | read_json(ROOT / "dataset/catalogue.json") | synthetic
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graphs", nargs="*", metavar="GRAPH",
                        help="graph names or all")
    parser.add_argument("--review", type=Path, help="check and rebuild coverage.tsv from an existing run")
    parser.add_argument("--output", type=Path, help="new run directory under output/baselines/")
    parser.add_argument("--query-name", choices=["test.tsv","benchmark.tsv"], default="benchmark.tsv")
    parser.add_argument("--b", type=int, default=1000)
    parser.add_argument("--d2-cap", type=int, default=128)
    parser.add_argument("--memory-gib", type=int, default=48)
    parser.add_argument("--kreach-memory-gib", type=int, default=96)
    parser.add_argument("--resume", action="store_true", help="resume the same run directory")
    parser.add_argument("--jobs", type=int, default=1, help="parallel graphs; each solver is single-threaded")
    args = parser.parse_args()
    if args.review:
        if args.graphs or args.output:
            parser.error("--review expects only an existing run directory")
        recorded = read_json(args.review / "run.json")
        write_coverage(args.review, recorded["graphs"], recorded.get("query_name","test.tsv"))
        return
    if not args.graphs or set(args.graphs) - (graphs.keys() | {"all"}):
        parser.error("choose all or one of " + ", ".join(sorted(graphs)))
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    selected = (sorted(graphs, key=lambda name: (graphs[name]["edges"], name))
                if "all" in args.graphs else list(dict.fromkeys(args.graphs)))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = (args.output or ROOT / "output/baselines" / stamp).resolve()
    output.mkdir(parents=True, exist_ok=args.resume)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    import hashlib
    source_hash = hashlib.sha256()
    for path in sorted((ROOT / "src").rglob("*")):
        if path.is_file() and path.suffix in (".py",".cpp",".hpp"):
            source_hash.update(str(path.relative_to(ROOT)).encode())
            source_hash.update(path.read_bytes())
    compiler = subprocess.check_output(["g++", "-dumpfullversion"], text=True).strip()
    metadata = dict(graphs=selected, timestamp=stamp, host=socket.gethostname(),
                    jobs=args.jobs, git_revision=revision, source_sha256=source_hash.hexdigest(), compiler=compiler,
                    query_name=args.query_name, b=args.b, d2_cap=args.d2_cap,
                    memory_gib=args.memory_gib, kreach_memory_gib=args.kreach_memory_gib, timeout=None)
    run_file = output / "run.json"
    if args.resume:
        prior = read_json(run_file)
        if any(prior.get(key)!=value for key,value in metadata.items() if key not in ("timestamp","jobs","git_revision")):
            raise ValueError("resume requires the same run configuration")
    else:
        run_file.write_text(json.dumps(metadata, indent=2)+"\n")
    for graph in selected:
        edges = ROOT / "dataset/prepared" / f"{graph}.edges"
        if not edges.exists():
            script = ("generate_synthetic.py" if graph in synthetic else
                      "prepare.py" if graph in ("wiki-Vote","p2p-Gnutella31") else "freeze.py")
            subprocess.run([sys.executable, ROOT/"src"/script,graph], check=True)
        if args.query_name=="benchmark.tsv" and not (WORKLOADS/graph/args.query_name).exists():
            subprocess.run([sys.executable, ROOT/"src/prepare_benchmark.py",graph],check=True)
    if not (ESTI_CACHE / "esti").exists():
        build_esti()
    search = compile_tool("search")
    # Finish online and partial-index families before expensive full-cover builds.
    import fcntl
    with (output / "run.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=args.jobs) as jobs:
            futures = [jobs.submit(run_family, name, graphs[name], family, output, search, args)
                       for family in FAMILIES for name in selected]
            for future in futures:
                future.result()
    write_coverage(output, selected, args.query_name)


if __name__ == "__main__":
    main()
