"""Resolve the exact frozen manifest entry for a benchmark input."""
import json
from pathlib import Path

QUERY_FILES = ("test.tsv", "benchmark.tsv", "benchmark-uniform.tsv", "benchmark-stratified.tsv")


def workload_spec(directory, filename):
    directory = Path(directory)
    if filename == "test.tsv":
        manifest = json.loads((directory/"manifest.json").read_text())
        return manifest, manifest["splits"]["test"]
    if filename in QUERY_FILES[1:]:
        manifest = json.loads((directory/"benchmark.json").read_text())
        if filename == "benchmark.tsv":
            return manifest, manifest["splits"]["benchmark"]
        return manifest, manifest["groups"][Path(filename).stem.removeprefix("benchmark-")]
    name = Path(filename)
    manifest = json.loads((directory/name.with_suffix(".json")).read_text())
    return manifest, manifest["splits"][name.stem]


def fixed_queries(path, k):
    with Path(path).open() as stream:
        header=stream.readline()
        selected=[line for line in stream if int(line.split("\t")[2])==k]
    return header+"".join(selected),len(selected)
