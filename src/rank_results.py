"""Rank exact graph-query methods by amortized end-to-end time, without figures."""
import argparse
from collections import defaultdict
import csv
import math
from pathlib import Path

from plot_pareto import points


def read(path):
    with path.open() as f:
        return list(csv.DictReader(f,delimiter="\t"))


def write(path, rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter="\t",lineterminator="\n")
        w.writeheader();w.writerows(rows)


def normalize_esti(rows):
    """The expanded ESTI binary changes only array capacity."""
    expanded={r["graph"]:r for r in rows if r["method"]=="esti_expanded" and r["status"]=="verified"}
    original_ok={r["graph"] for r in rows if r["method"]=="esti" and r["status"]=="verified"}
    result=[]
    for row in rows:
        method=row["method"]
        if method=="esti_expanded":
            if row["graph"] not in original_ok and row["status"]=="verified":
                result.append(dict(row,method="esti",variant=method))
        elif method!="esti" or row["graph"] not in expanded or row["graph"] in original_ok:
            result.append(row)
    return result


def size_scope(method):
    if method in ("bfs","bibfs"):return "zero_index"
    if method=="kreach":return "core_row_capacity"
    if method in ("scalable","gen-k-reach"):return "numeric_label_and_dense_core_payload"
    if method=="esti":return "author_reported_logical_index"
    if method in ("vcrea","vcrea-plus","pll"):return "encoded_label_stream"
    return "candidate_allocated_table" if "h@" in method or method.endswith("-h") else "method_reported"


def rank(rows, key, target, reverse=False):
    eligible=[r for r in rows if r.get(key) is not None]
    eligible.sort(key=lambda r:r[key],reverse=reverse)
    previous=None
    for i,row in enumerate(eligible,1):
        if previous is None or row[key]!=previous:
            position=i
        row[target]=position
        previous=row[key]


def evaluate(raw, volumes, strict=False):
    raw=normalize_esti(raw)
    variants={(r["graph"],r["method"]):r.get("variant") for r in raw}
    groups=defaultdict(list)
    for p in points(raw,strict=strict):groups[p["graph"]].append(p)
    result=[]
    for graph, group in groups.items():
        reference=next((p for p in group if p["method"]=="bibfs" and p["status"]=="verified"),None)
        if reference is None: raise ValueError(f"{graph}: verified Bi-BFS reference required")
        ref_us=reference["mean_us"]
        for p in group:
            verified=p["status"]=="verified"
            row=dict(p,variant=variants.get((graph,p["method"])),reference_us=ref_us,
                     index_size_scope=size_scope(p["method"]),timing_scope=p["timing_protocol"],
                     allocated_size_scope="persistent_auxiliary_allocation" if p.get("index_allocated_bytes") is not None else None,
                     query_speedup=None,queries_per_second=None,break_even_queries=None)
            if verified:
                latency=p["mean_us"]
                cost=p["build_s"]
                saving=ref_us-latency
                row["query_speedup"]=ref_us/latency
                row["queries_per_second"]=1e6/latency
                allocated=p.get("index_allocated_bytes")
                if allocated is not None and allocated>0:
                    row["cp_allocated_per_mib"]=row["query_speedup"]/(allocated/2**20)
                row["break_even_queries"]=math.ceil(cost*1e6/saving) if saving>0 else None
                q=p["queries"]
                row["as_measured_batch"]=ref_us/(latency+cost*1e6/q)
                for volume in volumes:
                    row[f"total_s_q{volume}"]=cost+volume*latency/1e6
                    row[f"as_q{volume}"]=ref_us/(latency+cost*1e6/volume)
                    if allocated is not None and allocated>0:
                        row[f"og_allocated_q{volume}_per_mib"]=row[f"as_q{volume}"]/(allocated/2**20)
            result.append(row)
        comparable=[r for r in result if r["graph"]==graph and r["status"]=="verified"]
        for key,target,descending in [
            ("build_s","rank_build",False),("mean_us","rank_query",False),
            ("index_payload_bytes","rank_reported_index",False),
            ("index_allocated_bytes","rank_allocated_index",False),
            ("ready_single_process_kib","rank_ready_rss",False),
            ("peak_single_process_kib","rank_peak_rss",False),
            ("as_measured_batch","rank_as_measured_batch",True),
        ]+[(f"as_q{q}",f"rank_as_q{q}",True) for q in volumes]:
            rank(comparable,key,target,descending)
    main=f"rank_as_q{volumes[0]}"
    return sorted(result,key=lambda r:(r["graph"],r.get(main,10**6),r["method"]))


def aggregate(rows, volumes, common_methods=None):
    graphs={r["graph"] for r in rows}
    verified=defaultdict(dict)
    for row in rows:
        if row["status"]=="verified":
            verified[row["method"]][row["graph"]]=row
    methods=sorted({r["method"] for r in rows})
    selected=common_methods or methods
    if set(selected)-set(methods):
        raise ValueError("unknown common comparison methods")
    common=set(graphs)
    for method in selected:
        common&=set(verified[method])
    result=[]
    for method in methods:
        available=verified[method]
        row=dict(method=method,verified_graphs=len(available),total_graphs=len(graphs),
                 common_graphs=len(common),common_graph_names=";".join(sorted(common)),
                 selected_for_common_comparison=method in selected)
        if common and common<=available.keys():
            for volume in volumes:
                scores=[available[g][f"as_q{volume}"] for g in common]
                row[f"geomean_as_q{volume}"]=math.exp(sum(math.log(x) for x in scores)/len(scores))
            speeds=[available[g]["query_speedup"] for g in common]
            row["geomean_query_speedup"]=math.exp(sum(math.log(x) for x in speeds)/len(speeds))
        result.append(row)
    for volume in volumes:
        rank([r for r in result if r["selected_for_common_comparison"]],
             f"geomean_as_q{volume}",f"rank_common_as_q{volume}",True)
    return sorted(result,key=lambda r:(r.get(f"rank_common_as_q{volumes[0]}",10**6),r["method"]))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("performance",type=Path,nargs="+")
    ap.add_argument("--output",type=Path)
    ap.add_argument("--query-volumes",nargs="+",type=int,default=[1000000,1000000000])
    ap.add_argument("--strict",action="store_true")
    ap.add_argument("--common-methods",nargs="+")
    a=ap.parse_args()
    if min(a.query_volumes)<=0:ap.error("query volumes must be positive")
    raw=[r for p in a.performance for r in read(p)]
    metrics=evaluate(raw,a.query_volumes,a.strict)
    summary=aggregate(metrics,a.query_volumes,a.common_methods)
    out=a.output or a.performance[0].parent/"ranking"
    out.mkdir(parents=True,exist_ok=True)
    write(out/"metrics.tsv",metrics)
    write(out/"aggregate.tsv",summary)
    print(len(metrics),"method/graph rows;",summary[0]["common_graphs"],"common graphs")


if __name__=="__main__":
    main()
