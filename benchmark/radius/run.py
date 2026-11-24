"""Compile the CPU pilot and measure one frozen graph, from the repository root."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = ROOT / "build/radius"


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def compile_tool(name):
    source = HERE / (name + ".cpp")
    binary = BUILD / name
    headers = list((ROOT / "src/radius").glob("*.hpp"))
    BUILD.mkdir(parents=True, exist_ok=True)
    if not binary.exists() or any(p.stat().st_mtime_ns > binary.stat().st_mtime_ns for p in [source, *headers]):
        with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
            fresh = Path(tmp) / name
            subprocess.run(["g++", "-O3", "-std=c++17", str(source), "-o", str(fresh)], check=True)
            fresh.replace(binary)
    return binary


def read_rows(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))


def prepare(name, n, edges, work):
    old = ROOT / "benchmark/workloads" / name
    used = {int(q["s"]) for path in sorted(old.glob("*.tsv")) for q in read_rows(path)}
    work.mkdir(parents=True, exist_ok=True)
    binary = compile_tool("workloads")
    excl = BUILD / (name + "-excluded.txt")
    excl.write_text("".join(f"{v}\n" for v in sorted(used)))
    subprocess.run([binary, str(n), edges, excl, work], check=True)
    manifest = dict(nodes=n, graph_sha256=digest(edges), seed=25112026, splits={})
    for split in ["train", "validation", "test"]:
        path = work / (split + ".tsv")
        rows = read_rows(path)
        sources = {int(q["s"]) for q in rows}
        if sources & used:
            raise ValueError("shared sources")
        used.update(sources)
        classes = {"within": 0, "beyond": 0, "unreachable": 0}
        for q in rows:
            d, k = int(q["d"]), int(q["k"])
            classes["unreachable" if d < 0 else "beyond" if d > k else "within"] += 1
        manifest["splits"][split] = dict(sha256=digest(path), queries=len(rows), sources=len(sources), **classes)
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--nodes", required=True, type=int)
    ap.add_argument("--fixed-k", choices=[2,4,6], type=int, help="select, build and evaluate using just this threshold")
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--output", type=Path, help="measurement directory; defaults to results/local/radius/<graph>")
    a = ap.parse_args()
    edges = ROOT / "dataset/prepared" / (a.graph + ".edges")
    work = HERE / "workloads" / a.graph
    if not (work / "manifest.json").exists() or a.prepare_only:
        prepare(a.graph, a.nodes, edges, work)
    if a.prepare_only:
        return
    manifest = json.loads((work / "manifest.json").read_text())
    if manifest["nodes"] != a.nodes or manifest["graph_sha256"] != digest(edges):
        raise ValueError("graph differs from workload manifest")
    for name, spec in manifest["splits"].items():
        if digest(work / (name + ".tsv")) != spec["sha256"]:
            raise ValueError("query file changed: " + name)
    dest = a.output or ROOT / "results/local/radius" / a.graph
    if a.fixed_k and not a.output:
        dest = dest / "fixed-k" / str(a.fixed_k)
    dest.mkdir(parents=True, exist_ok=True)
    binary = compile_tool("measure")
    subprocess.run(["/usr/bin/time", "-f", "%M", "-o", str(dest / "peak_kib.txt"),
                    binary, str(a.nodes), edges, work, dest, *([str(a.fixed_k)] if a.fixed_k else [])], check=True)
    print(a.graph, f"k={a.fixed_k}" if a.fixed_k else "mixed k",
          read_rows(dest / "repeats.tsv")[0]["n"], "test queries passed")


if __name__ == "__main__":
    main()
