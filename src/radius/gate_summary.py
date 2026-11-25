"""Summarize each group with paired repetitions; mark identical routing schedules."""
import argparse
from pathlib import Path
from statistics import median
import csv
import json
from run import ROOT, WORKLOADS, read_rows, digest


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph",required=True)
    ap.add_argument("--build",type=Path,required=True,help="build.tsv produced by run.py")
    ap.add_argument("--output",type=Path,help="directory containing gate-confirm.tsv")
    args=ap.parse_args();g=args.graph
    dest=args.output or ROOT/"output/adaptive-radius"/g
    conf=read_rows(dest/"gate-confirm.tsv")
    manifest=json.loads((WORKLOADS/g/"gate-holdouts/manifest.json").read_text())
    spec=json.loads((dest/"gate-provenance.json").read_text())
    if digest(args.build)!=spec["original_build_sha256"]: raise ValueError("changed index config")
    h={r["method"]:tuple(map(int,r["radii"].split(","))) for r in read_rows(args.build)}
    mask={(r["policy"],int(r["k"])):int(r["enabled"]) for r in read_rows(dest/"gate-decisions.tsv")}
    groups=sorted(manifest["splits"])
    def routing(name,k):
        if name=="bibfs": return ()
        policy=name.removeprefix("gated-")
        if not any(h[policy]) or (name.startswith("gated-") and not mask[policy,k]): return ()
        return h[policy]
    rows=[]
    for split in groups:
        n=manifest["splits"][split]["n"]
        qs=read_rows(WORKLOADS/g/"gate-holdouts"/(split+".tsv"))
        ks={int(q["k"]) for q in qs}
        subset=[r for r in conf if r["split"]==split]
        for comparator in ("gated-uniform","workload","bibfs"):
            def records(m):
                rs={int(r["repeat"]):r for r in subset if r["method"]==m}
                assert len(rs)==12 and set(rs)==set(range(1,13))
                assert all(int(r["n"])==n and int(r["errors"])==0 for r in rs.values())
                return [rs[i] for i in range(1,13)]
            a,b=records("gated-workload"),records(comparator)
            diff=[float(y["mean_us"])-float(x["mean_us"]) for x,y in zip(a,b)]
            rel=[v/float(y["mean_us"]) for v,y in zip(diff,b)]
            same=all(routing("gated-workload",k)==routing(comparator,k) for k in ks)
            if same: assert a[0]["scans"]==b[0]["scans"]
            rows.append(dict(split=split,n=n,comparator=comparator,same_policy=int(same),
                             gated_us=median(float(r["mean_us"]) for r in a),
                             comparator_us=median(float(r["mean_us"]) for r in b),
                             paired_us_saved=median(diff),paired_fraction_saved=median(rel),
                             faster_rounds=sum(v>0 for v in diff),
                             gated_scans=a[0]["scans"],comparator_scans=b[0]["scans"]))
    with (dest/"gate-summary.tsv").open("w") as f:
        wr=csv.DictWriter(f,fieldnames=rows[0].keys(),delimiter="\t",lineterminator="\n")
        wr.writeheader();wr.writerows(rows)


if __name__=="__main__":main()
