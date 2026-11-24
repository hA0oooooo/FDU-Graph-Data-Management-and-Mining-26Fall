"""Confirm frozen mixed-k policies on three disjoint groups of unseen sources."""
import argparse
import json
from pathlib import Path
import subprocess

from run import ROOT, HERE, BUILD, digest, compile_tool, read_rows


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--build", type=Path, required=True, help="frozen build.tsv for this graph")
    ap.add_argument("--balanced", action="store_true", help="balance method positions and predecessors, prewarm each batch")
    ap.add_argument("--output", type=Path, required=True)
    args=ap.parse_args()
    g=args.graph
    base=HERE/"workloads"/g
    manifest=json.loads((base/"manifest.json").read_text())
    edges=ROOT/"dataset/prepared"/(g+".edges")
    if digest(edges)!=manifest["graph_sha256"]:
        raise ValueError("graph changed")
    used=set()
    for folder in (ROOT/"benchmark/workloads"/g,base):
        for path in folder.glob("*.tsv"):
            used.update(int(r["s"]) for r in read_rows(path))
    folder=base/"holdouts"
    tracked=folder/"manifest.json"
    BUILD.mkdir(parents=True, exist_ok=True)
    if not tracked.exists():
        old=BUILD/(g+"-holdout-exclude.txt")
        old.write_text("".join(f"{s}\n" for s in sorted(used)))
        subprocess.run([compile_tool("workloads"),str(manifest["nodes"]),edges,old,folder,"confirm"],check=True)
    data=dict(seed=27112026,graph_sha256=manifest["graph_sha256"],splits={})
    for path in sorted(folder.glob("*.tsv")):
        rows=read_rows(path)
        sources={int(r["s"]) for r in rows}
        if sources & used:
            raise ValueError("held-out sources overlap")
        used.update(sources)
        data["splits"][path.stem]=dict(n=len(rows),sources=len(sources),sha256=digest(path))
    if set(data["splits"])!={"holdout-1","holdout-2","holdout-3"}:
        raise ValueError("missing holdout")
    if tracked.exists() and data!=json.loads(tracked.read_text()):
        raise ValueError("holdout differs from freeze")
    if not tracked.exists():
        tracked.write_text(json.dumps(data,indent=2)+"\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp=args.output.with_suffix(".part")
    with tmp.open("w") as f:
        subprocess.run([compile_tool("confirm"),str(manifest["nodes"]),edges,args.build,folder,
                        *(["balanced"] if args.balanced else [])],stdout=f,check=True)
    tmp.replace(args.output)
    print(g,sum(v["n"] for v in data["splits"].values()),"holdout queries passed",flush=True)


if __name__=="__main__":
    main()
