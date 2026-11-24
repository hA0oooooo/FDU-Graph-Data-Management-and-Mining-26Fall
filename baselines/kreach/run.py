"""Build and check the fixed-k K-Reach baseline on the frozen Wiki-Vote pilot."""

from collections import deque
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIELDS = (
    "k roots entries build_bfs_edge_scans build_ns process_peak_kib queries positives "
    "mismatches first_batch_ns median_batch_ns both_core source_core target_core neither_core"
).split()


def measure(binary, n, edges, workload, k):
    result = subprocess.check_output([binary, str(n), edges, workload, str(k)], text=True)
    return dict(zip(FIELDS, map(int, result.split()), strict=True))


def check_toy(binary, tmp):
    n = 9
    pairs = [(0, 0), (0, 1), (0, 2), (0, 7), (1, 0), (1, 2), (1, 5),
             (2, 3), (3, 1), (3, 4), (4, 5), (5, 3), (6, 0)]
    adj = [[] for _ in range(n)]
    for u, v in pairs:
        adj[u].append(v)
    edges = tmp / "toy.edges"
    edges.write_text("".join(f"{u}\t{v}\n" for u, v in pairs))
    workload = tmp / "toy.tsv"
    with workload.open("w") as file:
        file.write("s\tt\tk\td\n")
        for s in range(n):
            d = [-1] * n
            d[s] = 0
            queue = deque([s])
            while queue:
                u = queue.popleft()
                for v in adj[u]:
                    if d[v] < 0:
                        d[v] = d[u] + 1
                        queue.append(v)
            for t, distance in enumerate(d):
                for k in (2, 3, 4, 5, 6):
                    file.write(f"{s}\t{t}\t{k}\t{distance}\n")
    checked = [measure(binary, n, edges, workload, k) for k in (2, 3, 4, 5, 6)]
    return {"vertices": n, "directed_edges": len(pairs), "k": [2, 3, 4, 5, 6],
            "all_pairs_queries": sum(r["queries"] for r in checked),
            "mismatches": sum(r["mismatches"] for r in checked)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    edges = ROOT / "dataset/prepared/wiki-Vote.edges"
    workload = ROOT / "benchmark/workloads/wiki-Vote/test.tsv"
    manifest = json.loads((ROOT / "dataset/manifest.json").read_text())["wiki-Vote"]
    if sha(edges) != manifest["edges_sha256"]:
        raise ValueError("prepared graph differs from the frozen manifest")
    src = HERE / "kreach.cpp"
    flags = ["-O3", "-std=c++17"]
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        binary = tmp / "kreach"
        subprocess.run(["g++", *flags, src, "-o", binary], check=True)
        toy = check_toy(binary, tmp)
        rows = [measure(binary, manifest["nodes"], edges, workload, k) for k in (2, 4, 6)]
    total = {key: sum(row[key] for row in rows) for key in
             ("entries", "build_bfs_edge_scans", "build_ns", "queries", "positives", "mismatches")}
    if total["queries"] != len(workload.read_text().splitlines()) - 1:
        raise ValueError("the three K groups do not cover the test file")
    receipt = {
        "method": "K-Reach 2012 / independent fixed-k reimplementation",
        "compiler": subprocess.check_output(["g++", "-dumpfullversion"], text=True).strip(),
        "flags": flags, "platform": platform.system() + "-" + platform.machine(),
        "source_sha256": sha(src), "toy": toy, "dataset": "wiki-Vote",
        "vertices": manifest["nodes"], "edges": manifest["edges"],
        "edges_sha256": sha(edges), "workload_sha256": sha(workload),
        "runs": rows, "sum_of_three_independent_indexes": total,
    }
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
