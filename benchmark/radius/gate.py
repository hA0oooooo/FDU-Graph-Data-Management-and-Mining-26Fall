"""Freeze and confirm a per-k routing rule on unrelated source groups."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from run import ROOT, HERE, BUILD, read_rows, compile_tool, digest


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph",required=True)
    ap.add_argument("--cpu",type=int,default=13,help="Linux logical CPU for all measurements")
    ap.add_argument("--prepare-only",action="store_true")
    ap.add_argument("--output",type=Path,help="prefix directory for gate-* receipts")
    args=ap.parse_args()
    os.sched_setaffinity(0,{args.cpu})
    g=args.graph
    prev=HERE/"workloads"/g
    edges=ROOT/"dataset/prepared"/(g+".edges")
    base=ROOT/"results/round2"/g
    dest=args.output or ROOT/"results/local/radius"/g
    dest.mkdir(parents=True,exist_ok=True)
    m=json.loads((prev/"manifest.json").read_text())
    if digest(edges)!=m["graph_sha256"] or digest(prev/"validation.tsv")!=m["splits"]["validation"]["sha256"]:
        raise ValueError("graph or validation workload changed")
    if not (prev/"holdouts/manifest.json").is_file():
        raise ValueError("prior holdouts required before gating")
    used=set()
    for parent in (ROOT/"benchmark/workloads"/g,prev,prev/"holdouts"):
        for path in parent.glob("*.tsv"): used.update(int(q["s"]) for q in read_rows(path))
    output=prev/"gate-holdouts"
    output.mkdir(exist_ok=True)
    track=output/"manifest.json"
    if not track.exists():
        BUILD.mkdir(parents=True,exist_ok=True)
        exclude=BUILD/(g+"-gate-exclude.txt")
        exclude.write_text("".join(f"{v}\n" for v in sorted(used)))
        subprocess.run([compile_tool("workloads"),str(m["nodes"]),edges,exclude,output,"confirm","28112026"],check=True)
    meta=dict(seed=28112026,graph_sha256=m["graph_sha256"],excluded_source_count=len(used),splits={})
    for i in (1,2,3):
        path=output/f"holdout-{i}.tsv"
        rows=read_rows(path)
        sources={int(q["s"]) for q in rows}
        if not rows or sources & used: raise ValueError("empty or non-independent holdout")
        used.update(sources)
        meta["splits"][path.stem]=dict(n=len(rows),sources=len(sources),sha256=digest(path))
    if track.exists() and meta!=json.loads(track.read_text()):
        raise ValueError("gating workload changed")
    if not track.exists(): track.write_text(json.dumps(meta,indent=2)+"\n")
    if args.prepare_only:return
    binary=compile_tool("gate")
    spec=base/"build.tsv"
    subprocess.run([binary,str(m["nodes"]),edges,spec,prev/"validation.tsv",output,dest],check=True)
    spec_file=dict(graph_sha256=m["graph_sha256"],validation_sha256=m["splits"]["validation"]["sha256"],
                   original_build_sha256=digest(spec),holdout_manifest_sha256=digest(track),cpu=args.cpu,
                   evaluator_sha256=digest(HERE/"gate.cpp"),source_generator_sha256=digest(HERE/"workloads.cpp"),
                   index_sha256=digest(ROOT/"src/radius/index.hpp"),graph_header_sha256=digest(ROOT/"src/radius/graph.hpp"))
    (dest/"gate-provenance.json").write_text(json.dumps(spec_file,indent=2)+"\n")
    print(g,sum(s["n"] for s in meta["splits"].values()),"gate holdouts verified",flush=True)


if __name__=="__main__":main()
