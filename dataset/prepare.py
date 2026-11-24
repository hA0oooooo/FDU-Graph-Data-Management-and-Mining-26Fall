"""Freeze the two SNAP directed graphs; use cached originals when available."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent


def digest(path):
    with path.open("rb") as stream:
        sha = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
        return sha.hexdigest()


def prepare(name, spec):
    raw = ROOT / "raw" / spec["url"].rsplit("/", 1)[1]
    raw.parent.mkdir(exist_ok=True)
    if not raw.exists():
        partial = raw.with_suffix(".part")
        with urlopen(spec["url"], timeout=45) as response, partial.open("wb") as target:
            shutil.copyfileobj(response, target)
        if digest(partial) != spec["raw_sha256"]:
            raise ValueError(f"{name}: downloaded archive hash differs from manifest")
        partial.replace(raw)
    if digest(raw) != spec["raw_sha256"]:
        raise ValueError(f"{name}: cached archive hash differs from manifest")

    with gzip.open(raw, "rt", encoding="ascii") as stream:
        rows = [tuple(map(int, line.split())) for line in stream if line.strip() and not line.startswith("#")]
    vertices = sorted({vertex for edge in rows for vertex in edge})
    ids = {vertex: i for i, vertex in enumerate(vertices)}
    edges = sorted(set(rows))
    measured = (len(vertices), len(rows), len(edges), sum(u == v for u, v in edges))
    if measured != tuple(spec[key] for key in ("nodes", "rows", "edges", "self_loops")):
        raise ValueError(f"{name}: graph counts differ from manifest: {measured}")

    prepared = ROOT / "prepared"
    prepared.mkdir(exist_ok=True)
    graph = prepared / f"{name}.edges"
    staged = graph.with_suffix(".part")
    with staged.open("w", encoding="ascii", newline="\n") as stream:
        for u, v in edges:
            stream.write(f"{ids[u]}\t{ids[v]}\n")
    if digest(staged) != spec["edges_sha256"]:
        raise ValueError(f"{name}: prepared edge hash differs from manifest")
    staged.replace(graph)
    with (prepared / f"{name}.nodes.tsv").open("w", encoding="ascii", newline="\n") as stream:
        stream.write("dense_id\tsnap_id\n")
        for i, vertex in enumerate(vertices):
            stream.write(f"{i}\t{vertex}\n")
    print(f"{name}: {len(vertices):,} vertices, {len(edges):,} directed edges")


if __name__ == "__main__":
    manifest = json.loads((ROOT / "manifest.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graphs", nargs="*", metavar="GRAPH")
    args = parser.parse_args()
    for graph_name in args.graphs or manifest:
        prepare(graph_name, manifest[graph_name])
