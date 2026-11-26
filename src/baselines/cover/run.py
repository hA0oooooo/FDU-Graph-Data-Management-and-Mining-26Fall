"""Verify three directed label indexes against an independent workload."""
import argparse
from collections import deque
from functools import partial
import csv
import hashlib
import json
from pathlib import Path
import random
import resource
import subprocess
import tempfile
from time import perf_counter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
METHODS = ["vcrea", "vcrea-plus", "pll", "vcrea-strict", "vcrea-plus-strict"]
DEFAULT_MIB = 49152


def hash_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def limit_child(cap):
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def save(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2) + "\n")
    tmp.replace(path)


def write_requests(path, queries):
    path.write_text("".join(f"{s} {t} {k}\n" for s, t, k, _ in queries))


def measure(binary, name, method, n, edges, requests, queries, timeout, cap, progress=None):
    start = perf_counter()
    base = dict(graph=name, method=method, queries=len(queries))
    try:
        command = [binary, method, str(n), edges, requests, "1"]
        if progress is None:
            run = subprocess.run(command, capture_output=True, text=True,
                                 preexec_fn=partial(limit_child, cap), timeout=timeout)
        else:
            with progress.open("w") as log:
                run = subprocess.run(command, stdout=subprocess.PIPE, stderr=log, text=True,
                                     preexec_fn=partial(limit_child, cap), timeout=timeout)
    except subprocess.TimeoutExpired:
        return dict(base, status="timeout", elapsed_s=perf_counter()-start)
    if run.returncode:
        stderr = progress.read_text() if progress else run.stderr
        status = "allocation_failed" if "std::bad_alloc" in stderr else "failed"
        return dict(base, status=status, returncode=run.returncode,
                    stderr=stderr[-600:], elapsed_s=perf_counter()-start)
    result = json.loads(run.stdout)
    bits = result.pop("predictions")
    if len(bits) != len(queries) or set(bits) - {"0", "1"}:
        raise ValueError("invalid per-query response")
    classes = {c: {"n": 0, "mismatches": 0} for c in ("within_k", "beyond_k", "unreachable")}
    failures = []
    for bit, (s, t, k, d) in zip(bits, queries):
        group = classes["unreachable" if d < 0 else "within_k" if d <= k else "beyond_k"]
        group["n"] += 1
        if (bit == "1") != (0 <= d <= k):
            group["mismatches"] += 1
            if len(failures) < 10:
                failures.append((s, t, k, d, bit))
    return dict(base, **result, status="mismatch" if failures else "ok",
                by_class=classes, first_mismatches=failures, elapsed_s=perf_counter()-start)


def fixture_queries(n, edges):
    adj = [[] for _ in range(n)]
    inf = n+1
    floyd = [[0 if u == v else inf for v in range(n)] for u in range(n)]
    for u, v in edges:
        adj[u].append(v)
        floyd[u][v] = min(1, floyd[u][v])
    for m in range(n):
        for u in range(n):
            for v in range(n):
                floyd[u][v] = min(floyd[u][v], floyd[u][m] + floyd[m][v])
    rows = []
    for s in range(n):
        dist = [inf] * n
        dist[s] = 0
        queue = deque([s])
        while queue:
            u = queue.popleft()
            for v in adj[u]:
                if dist[v] == inf:
                    dist[v] = dist[u]+1
                    queue.append(v)
        assert dist == floyd[s]
        rows.extend((s,t,k,dist[t] if dist[t] < inf else -1)
                    for t in range(n) for k in range(n+1))
    return rows


def check_fixtures(binary, work, timeout, cap):
    rng = random.Random(2303470)
    graphs = [(7, [(3,0),(3,1),(0,4),(4,1),(1,2),(2,0),(1,5),(2,5)]),
              (5, [(0,0),(1,2),(2,1),(3,1),(1,3)]), (4, [])]
    for n in range(3,10):
        for p in (0.10,0.35,0.65):
            graphs.append((n, [(u,v) for u in range(n) for v in range(n) if rng.random()<p]))
    fixtures = [(n, edges, fixture_queries(n,edges)) for n,edges in graphs]
    # Exercises multi-byte hub ranks and distances in both label directions.
    n = 301
    chain = [(i,i+1) for i in range(n-1)]
    rows = [(s,t,k,t-s if t>=s else -1) for s in (0,12,140,290)
            for t in (0,10,128,270,300) for k in (0,1,127,128,256,299,300)]
    fixtures.append((n,chain,rows))
    methods = METHODS + ["vcrea-full", "vcrea-plus-full"]
    totals = {method: 0 for method in methods}
    for i, (n, edges, rows) in enumerate(fixtures):
        ep, qp = work/"fixture.edges", work/"fixture.q"
        ep.write_text("".join(f"{u} {v}\n" for u,v in edges))
        write_requests(qp,rows)
        stats = {}
        for method in methods:
            result = measure(binary,f"fixture-{i}",method,n,ep,qp,rows,timeout,cap)
            if result["status"] != "ok":
                raise ValueError(result)
            stats[method] = result["labels"]
            totals[method] += len(rows)
        assert stats["vcrea"] == stats["vcrea-full"]
        assert stats["vcrea-plus"] == stats["vcrea-plus-full"]
    return dict(graphs=len(fixtures), per_method_checked=totals, mismatches=0,
                full_bfs_equal_record_count_matches_pruned=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph")
    ap.add_argument("--nodes", type=int)
    ap.add_argument("--queries", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--methods", choices=METHODS, nargs="+", default=METHODS[:3])
    ap.add_argument("--timeout", type=int, help="optional wall seconds per method")
    ap.add_argument("--memory-mib", type=int, default=DEFAULT_MIB)
    ap.add_argument("--fixtures-only", action="store_true")
    args = ap.parse_args()
    if not args.fixtures_only and not (args.graph and args.queries):
        ap.error("provide --graph and --queries, or --fixtures-only")
    cap = args.memory_mib * 1024 ** 2
    src = HERE/"labels.cpp"
    flags = ["-O3", "-std=c++17"]
    report = dict(source_sha256=hash_file(src), compiler=subprocess.check_output(
        ["g++","-dumpfullversion"],text=True).strip(), flags=flags,
        child_address_cap_bytes=cap, wall_timeout_s=args.timeout, degree_threshold=1)
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        binary = work/"labels"
        subprocess.run(["g++",*flags,src,"-o",binary],check=True)
        if args.fixtures_only:
            report["fixtures"] = check_fixtures(binary,work,args.timeout,cap)
            save(args.output,report)
            return
        edges = ROOT/"dataset"/"prepared"/f"{args.graph}.edges"
        n = args.nodes
        if n is None:
            n = json.loads((ROOT/"dataset"/"manifest.json").read_text())[args.graph]["nodes"]
        with args.queries.open() as stream:
            queries = [tuple(int(row[key]) for key in ("s","t","k","d"))
                       for row in csv.DictReader(stream,delimiter="\t")]
        if not queries or any(not(0 <= s < n and 0 <= t < n and k>=0 and -1 <= d < n)
                              for s,t,k,d in queries):
            raise ValueError("invalid directed-distance workload")
        requests = work/"requests.txt"
        write_requests(requests,queries)
        report.update(graph=args.graph,nodes=n,edges_sha256=hash_file(edges),
                      queries_file=args.queries.name,queries_sha256=hash_file(args.queries),results=[])
        for method in args.methods:
            result = measure(binary,args.graph,method,n,edges,requests,queries,args.timeout,cap)
            report["results"].append(result)
            save(args.output,report)
            print(args.graph,method,result["status"],round(result["elapsed_s"],2),flush=True)
        if any(row["status"] != "ok" for row in report["results"]):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
