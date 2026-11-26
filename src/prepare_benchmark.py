"""Prepare reusable, disjoint benchmark queries and bind them to the graph hash."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import tempfile
from collections import Counter
import random

from radius.run import ROOT, WORKLOADS, BUILD, digest, compile_tool, read_rows


def generate(graph):
    work = WORKLOADS / graph
    original = json.loads((work / "manifest.json").read_text())
    edges = ROOT / "dataset/prepared" / (graph + ".edges")
    edge_hash = digest(edges)
    if edge_hash != original["graph_sha256"]:
        raise ValueError(f"{graph}: graph differs from manifest")
    out = work / "benchmark.tsv"
    manifest_path = out.with_suffix(".json")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if edge_hash != manifest["graph_sha256"] or digest(out) != manifest["splits"]["benchmark"]["sha256"]:
            raise ValueError(f"{graph}: existing benchmark changed")
        print(graph, manifest["splits"]["benchmark"]["queries"], "already frozen", flush=True)
        return
    previous_sources = set()
    for path in work.rglob("*.tsv"):
        if path.name not in ("benchmark.tsv", "benchmark-uniform.tsv", "benchmark-stratified.tsv"):
            previous_sources.update(int(q["s"]) for q in read_rows(path))
    prior = work / "prior-sources.txt"
    if prior.exists():
        previous_sources.update(map(int, prior.read_text().splitlines()))
    with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
        tmp = Path(tmp)
        exclusion = tmp / "excluded"
        exclusion.write_text("".join(f"{s}\n" for s in sorted(previous_sources)))
        files = [tmp / (label + ".tsv") for label in ("uniform", "stratified")]
        subprocess.run([compile_tool("benchmark_data"), str(original["nodes"]), edges, exclusion, *files], check=True)
        groups = {}
        all_rows, seen = [], set()
        for path in files:
            rows = read_rows(path)
            sources = {int(r["s"]) for r in rows}
            assert not sources & previous_sources
            previous_sources.update(sources)
            counts = Counter((r["k"], "unreachable" if int(r["d"])<0 else "within" if int(r["d"])<=int(r["k"]) else "beyond") for r in rows)
            ids = {(r["s"],r["t"],r["k"]) for r in rows}
            assert len(ids) == len(rows) and not ids & seen
            seen.update(ids)
            groups[path.stem] = dict(queries=len(rows), sources=len(sources),
                sha256=digest(path), classes={f"{k}:{c}":n for (k,c),n in sorted(counts.items())})
            all_rows.extend(rows)
            path.replace(work / f"benchmark-{path.stem}.tsv")
        random.Random(26112026).shuffle(all_rows)
        combined = tmp / "benchmark.tsv"
        with combined.open("w") as f:
            writer = csv.DictWriter(f, fieldnames=["s","t","k","d"], delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(all_rows)
        manifest = dict(nodes=original["nodes"], graph_sha256=edge_hash, seed=26112026,
                        splits={"benchmark": dict(sha256=digest(combined), queries=len(all_rows))}, groups=groups)
        combined.replace(out)
        manifest_path.write_text(json.dumps(manifest,indent=2)+"\n")
        print(graph, len(all_rows), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graphs", nargs="+")
    args = parser.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    for graph in args.graphs:
        generate(graph)
