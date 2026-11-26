"""Collect radius trials and matched baseline data without generating figures."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from plot_pareto import points


def read(path):
    with path.open() as f:
        return list(csv.DictReader(f,delimiter="\t"))


def write(path, rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w") as f:
        writer=csv.DictWriter(f,fieldnames=fields,delimiter="\t",lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(folder, baseline=None):
    rows=[]
    for path in sorted(folder.rglob("performance.tsv")):
        if not (path.parent/"build.tsv").exists():
            continue
        metadata=json.loads((path.parent/"run.json").read_text())
        builds={r["method"]:r for r in read(path.parent/"build.tsv")}
        for row in read(path):
            if (row["status"]!="verified" or int(row["checked"])!=metadata["queries"] or int(row["mismatches"]) or
                (row["graph_sha256"],row["query_sha256"])!=(metadata["graph_sha256"],metadata["query_sha256"])):
                raise ValueError(f"invalid trial: {path}")
            raw=Path(row["answers"]).parent.name
            build=builds[raw]
            radii=[int(x) for x in build["radii"].split(",")]
            active=sum(bool(a or b) for a,b in zip(radii[::2],radii[1::2]))
            saved=float(row["bibfs_median_query_us"])-float(row["median_query_us"])
            amortized=math.ceil(float(row["build_s"])*1e6/saved) if active and saved>0 else None
            rows.append(dict(row,query_name=metadata["query_name"],fixed_k=metadata["fixed_k"],
                       active_landmarks=active,
                       radii=build["radii"],break_even_queries=amortized,
                       trial=str(path.parent.relative_to(folder))))
    if not rows:
        raise ValueError("no completed trials")
    write(folder/"summary.tsv",rows)
    if baseline is not None:
        comparison=read(baseline)
        keys={(r["graph"],r["graph_sha256"],r["query_sha256"]) for r in comparison}
        for row in rows:
            if (row["graph"],row["graph_sha256"],row["query_sha256"]) in keys:
                comparison.append(dict(row,method=f'{row["method"]}@{row["label_budget_multiple"]}n'))
        candidates_for_front=[dict(r,status="no_active_index") if r.get("active_landmarks")==0 else r
                              for r in comparison]
        data=points(candidates_for_front,strict=True)
        write(folder/"matched_performance.tsv",comparison)
        write(folder/"matched_pareto_data.tsv",data)
    print(len(rows),"verified candidate configurations")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder",type=Path)
    parser.add_argument("--baseline",type=Path)
    args=parser.parse_args()
    summarize(args.folder,args.baseline)


if __name__=="__main__":
    main()
