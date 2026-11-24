"""Acquire and freeze additional directed graphs from the research catalogue."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
SPECS = json.loads((ROOT / "catalogue.json").read_text())


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def freeze(name, binary, stage):
    spec = SPECS[name]
    raw = ROOT / "raw" / spec["url"].rsplit("/", 1)[-1]
    raw.parent.mkdir(exist_ok=True)
    if not raw.is_file():
        partial = raw.with_suffix(raw.suffix + ".part")
        subprocess.run(["curl", "-fL", "--retry", "3", "-C", "-", "-o", partial, spec["url"]], check=True)
        subprocess.run(["gzip", "-t", partial], check=True)
        partial.replace(raw)
    frozen = ROOT / "frozen" / (name + ".json")
    expected = json.loads(frozen.read_text()) if frozen.exists() else None
    raw_sha = digest(raw)
    if expected and raw_sha != expected["raw_sha256"]:
        raise ValueError(f"{name}: raw archive hash differs from frozen version")
    # gzip -dc verifies the trailer CRC/length; for the tar case check the
    # entire stream also, since only one graph member is passed to the builder.
    if "member" in spec:
        subprocess.run(["gzip", "-t", raw], check=True)
        extract = ["tar", "-xOzf", raw, spec["member"]]
        fmt = "gra"
    else:
        extract = ["gzip", "-dc", raw]
        fmt = "edges"
    edges = stage / (name + ".edges")
    nodes = stage / (name + ".nodes.tsv")
    with subprocess.Popen(extract, stdout=subprocess.PIPE) as dec:
        normalized = subprocess.run([binary, fmt, str(spec["edges"]), edges, nodes],
                                    stdin=dec.stdout, capture_output=True, text=True, check=True)
        dec.stdout.close()
        if dec.wait():
            raise ValueError(f"{name}: decompression failed")
    n, rows, m, loops, isolated = map(int, normalized.stdout.split())
    if (n,m) != (spec["nodes"],spec["edges"]):
        raise ValueError(f"{name}: measured {(n,rows,m)} differs from catalogue")
    record = dict(nodes=n, rows=rows, edges=m, self_loops=loops, duplicates=rows-m,
                  isolated=isolated, raw_bytes=raw.stat().st_size, raw_sha256=raw_sha,
                  edges_bytes=edges.stat().st_size, edges_sha256=digest(edges),
                  node_map_sha256=digest(nodes))
    if expected and expected != record:
        raise ValueError(f"{name}: normalized graph differs from frozen record")
    frozen.parent.mkdir(exist_ok=True)
    staged_record = stage / (name + ".json")
    staged_record.write_text(json.dumps(record, indent=2) + "\n")
    staged_record.replace(frozen)
    nodes.replace(ROOT / "prepared" / nodes.name)
    edges.replace(ROOT / "prepared" / edges.name)
    print(name, n, m, record["edges_sha256"], flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("names", nargs="*", metavar="GRAPH")
    args = ap.parse_args()
    (ROOT / "prepared").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "prepared") as tmp:
        stage = Path(tmp)
        binary = stage / "normalize"
        subprocess.run(["g++", "-std=c++17", "-O2", ROOT / "normalize_large.cpp", "-o", binary], check=True)
        for name in args.names or SPECS:
            freeze(name, binary, stage)
