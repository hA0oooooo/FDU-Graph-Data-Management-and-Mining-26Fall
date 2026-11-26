"""Plot preprocessing-time versus mean query-latency Pareto fronts by graph."""
import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


def number(row, key):
    value=row.get(key)
    return float(value) if value else None


def points(rows, strict=False):
    """Compare only equal query workloads; sum fixed-k builds for mixed k."""
    by_graph=defaultdict(list)
    for row in rows:
        by_graph[row["graph"]].append(row)
    result=[]
    for graph, group in by_graph.items():
        hashes={(r["graph_sha256"],r["query_sha256"]) for r in group}
        if len(hashes)!=1:
            raise ValueError(f"{graph}: methods have different inputs")
        if len({r["method"] for r in group})!=len(group):
            raise ValueError(f"{graph}: duplicate method in comparison")
        if strict:
            keys=("execution_memory_gib","comparison_budget_gib","solver_threads","cpu_count","concurrent_configurations")
            protocols={(r.get("host"),r.get("cpu_affinity"),*(number(r,k) for k in keys)) for r in group if r["status"]=="verified"}
            if len(protocols)!=1 or any(v is None or v=="" for v in next(iter(protocols),())):
                raise ValueError(f"{graph}: verified methods have different or unknown resource settings")
        n=max(int(r["expected"]) for r in group)
        configs=defaultdict(list)
        for row in group:
            method=row["method"]
            if method.startswith(("kreach-","scalable-")):
                method=method.rsplit("-",1)[0]
            configs[method].append(row)
        graph_points=[]
        for method, variants in configs.items():
            ready=all(r["status"]=="verified" and number(r,"mismatches")==0 for r in variants) and sum(int(r["checked"]) for r in variants)==n
            base=dict(graph=graph,method=method,queries=n,configurations=len(variants),
                      status="verified" if ready else "incomplete",build_s=None,batch_s=None,mean_us=None,
                      index_payload_bytes=None,peak_single_process_kib=None,pareto=False)
            if ready:
                payload=[number(r,"index_payload_bytes") for r in variants]
                peak=[number(r,"process_peak_kib") for r in variants]
                base.update(build_s=sum(float(r["build_s"]) for r in variants),
                            batch_s=sum(float(r["batch_s"]) for r in variants),
                            index_payload_bytes=sum(payload) if all(v is not None for v in payload) else None,
                            peak_single_process_kib=max(peak) if all(v is not None for v in peak) else None)
                base["mean_us"]=base["batch_s"]*1e6/n
                budgets={number(r,"comparison_budget_gib") for r in variants}
                if len(budgets)==1 and None not in budgets and base["index_payload_bytes"] is not None:
                    if base["index_payload_bytes"]>next(iter(budgets))*2**30:
                        base["status"]="payload_exceeds_budget"
            else:
                base["status"]=";".join(sorted({r["status"] for r in variants}))
            graph_points.append(base)
        valid=[p for p in graph_points if p["status"]=="verified"]
        for p in valid:
            p["pareto"]=not any(q["build_s"]<=p["build_s"] and q["mean_us"]<=p["mean_us"] and
                               (q["build_s"]<p["build_s"] or q["mean_us"]<p["mean_us"]) for q in valid)
        result.extend(graph_points)
    return result


def draw(data, folder):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    by_graph=defaultdict(list)
    for row in data:
        if row["status"]=="verified":
            by_graph[row["graph"]].append(row)
    labels={"bfs":"BFS","bibfs":"Bi-BFS","esti":"ESTI","esti_expanded":"ESTI (expanded)",
            "kreach":"K-Reach","scalable":"Scalable K-Reach","gen-k-reach":"gen-k-reach",
            "vcrea":"VCRea","vcrea-plus":"VCRea+","pll":"Directed PLL"}
    from matplotlib.lines import Line2D
    markers={"bfs":"o","bibfs":"s","esti":"^","esti_expanded":"v","kreach":"D",
             "scalable":"P","gen-k-reach":"X","vcrea":"h","vcrea-plus":"*","pll":"<"}
    for graph, rows in sorted(by_graph.items()):
        fig,ax=plt.subplots(figsize=(7.6,5.5),layout="constrained")
        positive=[p["build_s"] for p in rows if p["build_s"]>0]
        threshold=min(positive)/10 if positive else .001
        ax.set_xscale("symlog",linthresh=threshold)
        ax.set_yscale("log")
        if positive:
            low=math.ceil(math.log10(min(positive)))
            high=math.floor(math.log10(max(positive)*1.5))
            decades=list(range(low,high+1))
            ticks=[0]+[10**i for i in decades]
            ax.set_xticks(ticks,["0"]+[f"$10^{{{i}}}$" for i in decades])
            ax.set_xlim(-threshold*.4,max(positive)*1.5)
        ax.grid(True,color="#dce2e8",linewidth=.65,alpha=.8)
        for p in sorted(rows,key=lambda x:x["pareto"]):
            color="#165d9c" if p["pareto"] else "#9ba8b4"
            ax.scatter(p["build_s"],p["mean_us"],s=68,marker=markers.get(p["method"],"o"),
                       color=color,edgecolor="white",linewidth=.6,zorder=3)
        front=sorted((p for p in rows if p["pareto"]),key=lambda p:p["build_s"])
        ax.plot([p["build_s"] for p in front],[p["mean_us"] for p in front],
                color="#165d9c",linewidth=1.25,alpha=.85,zorder=2)
        ax.set_title(f"{graph}   ·   {rows[0]['queries']:,} queries",loc="left",fontweight="semibold")
        ax.set_xlabel("Index construction time (s)")
        ax.set_ylabel("Mean query latency (µs)")
        ax.margins(y=.16)
        handles=[Line2D([],[],marker=markers.get(p["method"],"o"),linestyle="none",
                        markerfacecolor="#165d9c" if p["pareto"] else "#9ba8b4",
                        markeredgecolor="white",markersize=8,label=labels.get(p["method"],p["method"]))
                 for p in rows]
        handles.append(Line2D([],[],color="#165d9c",label="Pareto frontier"))
        ax.legend(handles=handles,frameon=False,loc="upper center",bbox_to_anchor=(.5,-.18),
                  ncol=3,fontsize=9,columnspacing=1.1,handletextpad=.5)
        fig.savefig(folder/(graph+".pdf"))
        fig.savefig(folder/(graph+".png"),dpi=180)
        plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("performance",type=Path,nargs="+")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--strict",action="store_true",help="require identical documented resource settings")
    parser.add_argument("--table-only",action="store_true",help="calculate front without Matplotlib")
    args=parser.parse_args()
    rows=[]
    for path in args.performance:
        with path.open() as f:
            rows.extend(csv.DictReader(f,delimiter="\t"))
    data=points(rows,args.strict)
    output=args.output or args.performance[0].parent/"pareto"
    output.mkdir(parents=True,exist_ok=True)
    with (output/"pareto.tsv").open("w") as f:
        writer=csv.DictWriter(f,fieldnames=list(data[0]),delimiter="\t",lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)
    if not args.table_only:
        draw(data,output)
    print(len(data),"method/graph points;",sum(r["pareto"] for r in data),"non-dominated")


if __name__=="__main__":
    main()
