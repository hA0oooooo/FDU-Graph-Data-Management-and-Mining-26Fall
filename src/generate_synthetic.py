"""Generate directed ER graphs at fixed size and different densities."""
import argparse
import json
import random
from pathlib import Path
import tempfile
from radius.run import ROOT, digest


def generate(name, spec):
    target = ROOT / "dataset/prepared"
    target.mkdir(parents=True, exist_ok=True)
    rng = random.Random(spec["seed"])
    n = spec["nodes"]
    with tempfile.TemporaryDirectory(dir=target) as tmp:
        edges, nodes = Path(tmp)/"graph.edges", Path(tmp)/"nodes.tsv"
        count = 0
        with edges.open("w") as out:
            for u in range(n):
                for v in range(n):
                    if u != v and rng.random() < spec["probability"]:
                        out.write(f"{u}\t{v}\n")
                        count += 1
        with nodes.open("w") as f:
            f.write("node_id\toriginal_id\n")
            for u in range(n):
                f.write(f"{u}\t{u}\n")
        if count != spec["edges"]:
            raise ValueError(f"{name}: synthetic edge count differs")
        record = dict(nodes=n, edges=count, seed=spec["seed"], probability=spec["probability"],
                      edges_sha256=digest(edges), node_map_sha256=digest(nodes))
        frozen = ROOT/"dataset/frozen"/f"{name}.json"
        if frozen.exists() and record != json.loads(frozen.read_text()):
            raise ValueError(f"{name}: synthetic graph differs from freeze")
        frozen.write_text(json.dumps(record,indent=2)+"\n")
        edges.replace(target/f"{name}.edges")
        nodes.replace(target/f"{name}.nodes.tsv")
        print(name,n,count,flush=True)


if __name__ == "__main__":
    specs=json.loads((ROOT/"dataset/synthetic.json").read_text())
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graphs",nargs="*",choices=list(specs))
    args=parser.parse_args()
    for g in args.graphs or specs:
        generate(g,specs[g])
