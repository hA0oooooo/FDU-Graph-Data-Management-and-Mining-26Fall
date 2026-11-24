"""Reproduce one graph end-to-end on a Linux CPU, using the frozen inputs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from run import ROOT, HERE, compile_tool


def launch(script, *args):
    subprocess.run([sys.executable, ROOT / script, *map(str, args)], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    workloads = HERE / "workloads"
    names = sorted(p.parent.name for p in workloads.glob("*/manifest.json"))
    parser.add_argument("graph", choices=[*names, "all"])
    parser.add_argument("--historical", action="store_true", help="also build each historical baseline")
    args = parser.parse_args()
    legacy = json.loads((ROOT / "dataset/manifest.json").read_text())
    for graph in names if args.graph == "all" else [args.graph]:
        work = workloads / graph
        edges = ROOT / "dataset/prepared" / (graph + ".edges")
        if not edges.exists():
            launch("dataset/prepare.py" if graph in legacy else "dataset/freeze.py", graph)
        spec = legacy.get(graph) or json.loads((ROOT / "dataset/frozen" / (graph + ".json")).read_text())
        n = str(spec["nodes"])
        dest = ROOT / "results/local/radius" / graph
        main_args = ["--graph", graph, "--nodes", n]
        launch("benchmark/radius/run.py", *main_args)
        for k in (2, 4, 6):
            launch("benchmark/radius/run.py", *main_args, "--fixed-k", k)
        config = dest / "build.tsv"
        test = work / "test.tsv"
        launch("benchmark/radius/confirm.py", "--graph", graph, "--build", config,
               "--balanced", "--output", dest / "holdouts-balanced.tsv")
        for tool, output, extra in [
            ("audit", "audit", [work]),
            ("filters", "filters", [test]),
            ("matched", "matched", [test, config]),
            ("routes", "routes", [test, config]),
            ("serve", "native-batch", [test, config]),
        ]:
            path = dest / (output + ".tsv")
            partial = path.with_suffix(".part")
            with partial.open("w") as stream:
                subprocess.run([compile_tool(tool), n, edges, *extra], stdout=stream, check=True)
            partial.replace(path)
        if args.historical:
            part = dest / "historical.json"
            legacy_args = [*main_args, "--edges", spec["edges"]]
            launch("benchmark/radius/historical.py", *legacy_args, "--output", part)
            if any(r["status"] == "time_limit" for r in json.loads(part.read_text())["kreach"]):
                launch("benchmark/radius/historical.py", *legacy_args, "--extend-from", part,
                       "--output", dest / "historical-extended.json")
            large = spec["nodes"] >= 100_000
            launch("baselines/scalable/run.py", "--graph", edges, "--nodes", n, "--queries", test,
                   "--b", 16 if large else 1000, "--d2-cap", 4 if large else 32,
                   "--output", dest / "scalable.json")
            launch("baselines/cover/matrix.py", graph, "--output", ROOT / "results/local/cover")


if __name__ == "__main__":
    main()
