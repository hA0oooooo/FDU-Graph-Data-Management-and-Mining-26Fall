"""Compare every ESTI answer to independent distances on the identical workload."""
import argparse
import csv
import hashlib
import json
import re
import resource
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter

from build import BUILD, HERE, REV

REPO = HERE.parents[1]
GRAPHS = ["wiki-Vote", "p2p-Gnutella31"]


def fixtures():
    # Each graph has a directed cycle, a sink and an isolated vertex. The
    # second has many zero-indegree vertices to trigger upstream graph reversal.
    graphs = {
        "cycle-isolate": [[1, 3], [2], [0, 3], [4], [], []],
        "reverse-and-isolate": [[5], [5], [5], [5], [5], [6], [5, 7], [], []],
    }
    for name, out in graphs.items():
        n = len(out)
        # Independent Floyd-Warshall distances; all ordered pairs and all k.
        dist = [[0 if u == v else n + 1 for v in range(n)] for u in range(n)]
        for u, neighbors in enumerate(out):
            for v in neighbors:
                dist[u][v] = 1
        for m in range(n):
            for u in range(n):
                for v in range(n):
                    dist[u][v] = min(dist[u][v], dist[u][m] + dist[m][v])
        queries = [(s, t, k, dist[s][t] if dist[s][t] < n else -1)
                   for s in range(n) for t in range(n) for k in range(n + 1)]
        yield name, out, queries


def load_graph(name, split):
    prepared = REPO / "dataset" / "prepared"
    node_path = prepared / f"{name}.nodes.tsv"
    edge_path = prepared / f"{name}.edges"
    with node_path.open() as f:
        out = [[] for _ in csv.DictReader(f, delimiter="\t")]
    with edge_path.open() as f:
        for line in f:
            u, v = map(int, line.split())
            out[u].append(v)
    query_path = REPO / "benchmark" / "workloads" / name / f"{split}.tsv"
    with query_path.open() as f:
        queries = [tuple(int(row[key]) for key in ("s", "t", "k", "d"))
                   for row in csv.DictReader(f, delimiter="\t")]
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (node_path, edge_path, query_path)}
    return out, queries, hashes


def check(name, out, queries):
    if not queries:
        raise ValueError(f"No queries for {name}")
    m = sum(map(len, out))
    with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
        work = Path(tmp)
        with (work / "graph").open("w") as f:
            print(len(out), m, sep="\n", file=f)
            for u, neighbors in enumerate(out):
                print(u, len(neighbors), *neighbors, sep="\t", file=f)
        with (work / "queries").open("w") as f:
            for s, t, k, _ in queries:
                # The kernel receives no reference answers.
                print(s, t, -2, k, file=f)
        started = perf_counter()
        result = subprocess.run(["/usr/bin/time", "-f", "%M", "-o", "rss-kib",
                                 BUILD / "esti", "graph", "queries", "cyc"],
                                cwd=work, capture_output=True, text=True, check=True, timeout=180)
        process_ms = 1000 * (perf_counter() - started)
        predictions = (work / "answers.txt").read_text().splitlines()
        peak = int((work / "rss-kib").read_text().strip())
    if len(predictions) != len(queries) or set(predictions) - {"0", "1"}:
        raise ValueError(f"Invalid ESTI output for {name}")
    errors, kinds = [], {"within_k": 0, "beyond_k": 0, "unreachable": 0}
    for q, bit in zip(queries, predictions):
        s, t, k, d = q
        truth = 0 <= d <= k
        kinds["within_k" if truth else "unreachable" if d == -1 else "beyond_k"] += 1
        if (bit == "1") != truth:
            errors.append({"s": s, "t": t, "k": k, "d": d, "prediction": int(bit)})
    log = result.stdout
    return dict(name=name, nodes=len(out), edges=m, queries=len(queries), truth_groups=kinds,
                mismatches=len(errors), first_mismatches=errors[:10],
                reversed_by_author="the graph has been reversed" in log,
                logical_index_bytes=int(re.search(r"index size: (\d+) bytes", log)[1]),
                build_ms=float(re.search(r"construction time: ([\d.]+) ms", log)[1]),
                batch_query_ms=float(re.search(r"query time: ([\d.]+) ms", log)[1]),
                process_ms=round(process_ms, 3), process_peak_kib=peak)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("graphs", nargs="*", help="prepared graphs (fixtures always run)")
    ap.add_argument("--split", choices=("test", "confirmation"), default="test")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    for name in args.graphs:
        if name not in GRAPHS:
            ap.error(f"Available data: {', '.join(GRAPHS)}")
    # Tarjan's DFS in the author implementation is recursive. This limit is a
    # ceiling, not reserved memory, and applies only to the verifier and children.
    soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    if soft != resource.RLIM_INFINITY and soft < 256 * 1024**2:
        resource.setrlimit(resource.RLIMIT_STACK,
                           (256 * 1024**2 if hard == resource.RLIM_INFINITY else min(hard, 256 * 1024**2), hard))
    rows = [check(name, out, qs) for name, out, qs in fixtures()]
    for name in args.graphs:
        out, qs, hashes = load_graph(name, args.split)
        rows.append(dict(check(name, out, qs), input_sha256=hashes))
    report = json.dumps(dict(split=args.split, upstream_commit=REV, compiler=subprocess.check_output(
        ["g++", "-dumpfullversion"], text=True).strip(), results=rows), indent=2) + "\n"
    if args.output:
        args.output.write_text(report)
    print(report, end="")
    if any(row["mismatches"] for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
