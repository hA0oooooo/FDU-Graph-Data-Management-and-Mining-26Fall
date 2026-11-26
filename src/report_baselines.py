"""Inspect baseline runs using a common table of exactness and resource metrics."""
import argparse
import csv
import json
import os
from pathlib import Path
from collections import Counter
from baselines.cover.capacity_report import verify as verify_label_capacity
from radius.run import WORKLOADS, digest, read_rows
from workload import workload_spec


def load(path):
    return json.loads(path.read_text())


def read_config(run_dir, run, graph):
    query = WORKLOADS / graph / run.get("query_name", "test.tsv")
    manifest, frozen = workload_spec(query.parent,query.name)
    if digest(query)!=frozen["sha256"]:
        raise ValueError(f"{graph}: query hash mismatch")
    if run.get("fixed_k") is not None:
        selected=run_dir/"inputs"/(graph+".tsv")
        meta,spec=workload_spec(selected.parent,str(selected.resolve()))
        if (meta["source_sha256"]!=frozen["sha256"] or meta["graph_sha256"]!=manifest["graph_sha256"] or
            meta["fixed_k"]!=run["fixed_k"] or digest(selected)!=spec["sha256"]):
            raise ValueError(f"{graph}: fixed query identity mismatch")
        query,frozen=selected,spec
    truth=[(int(q["k"]),int(q["d"])) for q in read_rows(query)]
    counts=Counter(k for k,_ in truth)
    if len(truth)!=frozen["queries"] or (run.get("fixed_k") is not None and set(counts)!={run["fixed_k"]}):
        raise ValueError(f"{graph}: query count or threshold mismatch")
    return manifest["graph_sha256"], frozen["sha256"], frozen["queries"], counts, truth


def capacity_status(run_dir, graph, receipt, row):
    """A cancelled build is capacity-proved only with a matching strict lower bound."""
    if "bad_alloc" in row.get("detail", ""):
        return "allocation_failed"
    path = run_dir / "capacity_decisions.json"
    if row.get("code") != -15 or not path.exists():
        return row["status"]
    decisions = [d for d in load(path) if d["graph"] == graph and d["k"] == row["k"]]
    if not decisions:
        return row["status"]
    if len(decisions) != 1:
        raise ValueError("duplicate capacity evidence")
    decision = decisions[0]
    proof = decision["proof"]
    if (decision["graph_sha256"] != receipt["graph_sha256"] or
        decision["test_sha256"] != receipt["test_sha256"] or
        decision["memory_gib"] != row["memory_gib"] or
        proof["graph"] != graph or int(proof["k"]) != row["k"] or
        int(proof["payload_lower_bytes"]) <= row["memory_gib"] * 2**30):
        raise ValueError(f"{graph}: invalid K-Reach capacity certificate")
    return "capacity_proved"


def label_capacity_status(run_dir, graph, method, receipt, row, original=True):
    path=run_dir/"label_capacity_decisions.json"
    if row.get("returncode")!=-15:
        return row["status"]
    decisions=[d for d in load(path) if (d["graph"],d["method"])==(graph,method)] if path.exists() else []
    if not decisions:
        previous=run_dir/"protocol-decisions.json"
        if original and previous.exists() and any((d["graph"],d["method"],d["query_sha256"],d["source_sha256"])==
                  (graph,method,receipt["queries_sha256"],receipt["source_sha256"]) for d in load(previous)):
            retries=run_dir/"retry-labels.json"
            if retries.exists():
                for job in load(retries):
                    if (job["graph"],job["method"])!=(graph,method):
                        continue
                    proc=Path(f'/proc/{job["pid"]}/cmdline')
                    if proc.exists():
                        try:
                            argv=proc.read_bytes().decode().strip("\0").split("\0")
                        except FileNotFoundError:
                            argv=[]
                        if any(v.endswith("baselines/cover/matrix.py") for v in argv) and graph in argv and method in argv:
                            return "running"
            return "superseded_protocol"
        return row["status"]
    if len(decisions)!=1:
        raise ValueError("duplicate label capacity evidence")
    d=decisions[0]
    proof=d["proof"]
    if (d["graph_sha256"]!=receipt["edges_sha256"] or d["query_sha256"]!=receipt["queries_sha256"] or
        d["source_sha256"]!=receipt["source_sha256"] or
        d["memory_gib"]*2**30!=receipt["child_address_cap_bytes"] or
        (proof["graph"],proof["method"],proof["memory_gib"])!=(graph,method,d["memory_gib"])):
        raise ValueError(f"{graph}: label capacity certificate input mismatch")
    verify_label_capacity(proof)
    return "capacity_proved"


def records(run_dir, graph, config):
    edge_hash, query_hash, expected, counts, truth = read_config(run_dir,config,graph)
    method_layout=config.get("layout")=="method"
    def dest(family):
        return run_dir/"methods"/family/graph if method_layout else run_dir/graph
    result = {}
    def item(name, row, status, checked=None, errors=None, build=None, query=None, size=None, rss=None, source=None, limit=None, builder=None):
        fixed=int(name.rsplit("-",1)[1]) if name.startswith(("scalable-","kreach-")) else None
        n=counts[fixed] if fixed is not None else expected
        valid=status in ("passed","verified","ok")
        answer_path=None
        if valid and source:
            candidate=source.with_suffix(".answers.tsv") if name in ("vcrea","vcrea-plus","pll") else source.parent/"answers"/(name+".tsv")
            if candidate.exists():
                answers=[r["answer"] for r in read_rows(candidate)]
                expected_bits=[str(int(0<=d<=k)) for k,d in truth if fixed is None or k==fixed]
                if len(answers)!=n or set(answers)-{"0","1"} or sum(a!=b for a,b in zip(answers,expected_bits))!=errors:
                    raise ValueError(f"{candidate}: stored answers disagree with receipt")
                answer_path=str(candidate.relative_to(run_dir))
        result[name] = dict(graph=graph, method=name,
             status=("verified" if checked==n and errors==0 else "invalid") if valid else status,
             expected=n, checked=checked if valid else None, mismatches=errors if valid else None,
             build_s=build if valid else None, batch_s=query if valid else None,
             mean_us=query*1e6/n if valid and query is not None else None,
             index_payload_bytes=size if valid else None, process_peak_kib=rss if valid else None,
             query_sha256=query_hash, graph_sha256=edge_hash,
             receipt=str(source.relative_to(run_dir)) if source else None,
             answers=answer_path, builder=builder, execution_memory_gib=limit,
             comparison_budget_gib=config.get("comparison_budget_gib",config.get("memory_gib")),
             solver_threads=config.get("solver_threads",1),
             host=config.get("host"),cpu_affinity=",".join(map(str,config.get("cpu_affinity",[]))) or None,
             cpu_count=len(config.get("cpu_affinity",[])) or None,
             concurrent_configurations=config.get("jobs"))

    search=dest("search")/"search.tsv"
    if search.exists():
        peak=search.parent/"peak-kib.txt"
        for r in read_rows(search):
            item(r["method"],r,"verified",int(r["queries"]),int(r["mismatches"]),0,
                 float(r["batch_ms"])/1000,0,int(peak.read_text()) if peak.exists() else None,
                 source=search,limit=config.get("memory_gib") if method_layout else None)
    historical = dest("esti")/"historical.json"
    files = [historical] if historical.exists() else [dest("esti")/"esti.json",dest("kreach")/"kreach.json"]
    profile=run_dir/"esti-profile"/(graph+".json")
    if profile.exists():
        files.append(profile)
    for file in files:
        if not file.exists():
            continue
        r = load(file)
        if (r["graph_sha256"],r["test_sha256"])!=(edge_hash,query_hash):
            raise ValueError(f"{file}: input mismatch")
        for method in ("esti","esti_expanded"):
            if method in r:
                row=r[method]
                item(method,row,row["status"],row.get("queries"),row.get("mismatches"),
                     row.get("build_ms",0)/1000,row.get("batch_ms",0)/1000,
                     row.get("index_bytes"),row.get("process_peak_kib"),source=file,limit=row.get("memory_gib"))
        for row in r.get("kreach",[]):
            status=capacity_status(run_dir, graph, r, row)
            item(f"kreach-{row['k']}",row,status,row.get("queries"),row.get("mismatches"),
                 row.get("build_ns",0)/1e9,row.get("first_batch_ns",0)/1e9,
                 row.get("index_bytes"),row.get("process_peak_kib"),source=file,limit=row.get("memory_gib"))
    file=dest("scalable")/"scalable.json"
    if file.exists():
        r=load(file)
        if (r["graph_sha256"],r["workload_sha256"])!=(edge_hash,query_hash):
            raise ValueError(f"{file}: input mismatch")
        for row in r["runs"]:
            method="gen-k-reach" if row["mode"]=="general" else f"scalable-{row['mode']}"
            size=None
            if "D1" in row and "D2" in row:
                size=sum(8*row[d]["endpoint_labels"]+4*row[d]["dense_core_slots"] for d in ("D1","D2"))
            item(method,row,row["status"],row.get("n_queries"),row.get("errors"),row.get("build_s"),
                 row.get("queries_s"),size,row.get("peak_rss_kib"),source=file,limit=r.get("address_space_gib"))
    for method in ("vcrea","vcrea-plus","pll"):
        file=(dest(method) if method_layout else run_dir/"labels"/graph)/(method+".json")
        parallel=run_dir/"parallel-labels"/graph/(method+".json")
        if parallel.exists():
            file=parallel
        retry=run_dir/"methods"/method/graph/(method+".json")
        if not method_layout and retry.exists():
            file=retry
        packed=run_dir/"packed-labels"/graph/(method+".json")
        if packed.exists() and load(packed)["results"][0]["status"]=="ok":
            if not file.exists() or load(file)["results"][0]["status"]!="ok":
                file=packed
        if not file.exists():
            continue
        r=load(file)
        if (r["edges_sha256"],r["queries_sha256"])!=(edge_hash,query_hash):
            raise ValueError(f"{file}: input mismatch")
        if (r.get("child_address_cap_bytes") not in (None, config.get("memory_gib",0)*2**30)
                and config.get("query_name","test.tsv")!="test.tsv"):
            raise ValueError(f"{file}: memory cap differs")
        row=r["results"][0]
        if row["method"]!=method:
            raise ValueError(f"{file}: method mismatch")
        classes=row.get("by_class")
        checked=sum(c["n"] for c in classes.values()) if classes else None
        errors=sum(c["mismatches"] for c in classes.values()) if classes else None
        item(method,row,label_capacity_status(run_dir,graph,method,r,row,original=file!=retry),checked,errors,row.get("build_ns",0)/1e9,
             row.get("query_ns",0)/1e9,row.get("encoded_bytes"),row.get("process_peak_kib"),source=file,limit=r.get("child_address_cap_bytes",0)/2**30 or None,builder=r.get("builder","scalar"))

    methods = ["bfs","bibfs","esti","gen-k-reach","vcrea","vcrea-plus","pll"]
    methods += [f"{name}-{k}" for name in ("scalable","kreach") for k in sorted(counts)]
    if ("esti_expanded" in result or (result.get("esti") and
                     result["esti"]["status"]=="exceeds_upstream_capacity")):
        methods.append("esti_expanded")
    for method in methods:
        if method not in result:
            item(method,{}, "pending")
    return [result[m] for m in methods]


def write_table(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".part")
    with tmp.open("w") as file:
        writer=csv.DictWriter(file,fieldnames=rows[0],delimiter="\t",lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def write_method_results(output, rows, source_runs=None):
    """Keep construction and query results together under each method."""
    for row in rows:
        method=row["method"]
        family,variant=method,None
        if method.startswith(("kreach-","scalable-")):
            family,k=method.rsplit("-",1)
            variant="k"+k
        elif method.startswith("esti"):
            family,variant="esti","expanded" if method=="esti_expanded" else "original"
        target=output/"methods"/family/row["graph"]
        if variant:
            target=target/variant
        target.mkdir(parents=True,exist_ok=True)
        raw_root=source_runs[row["run"]] if source_runs else output
        raw=raw_root/row["receipt"] if row.get("receipt") else None
        answer=raw_root/row["answers"] if row.get("answers") else None
        identity={k:row[k] for k in ("graph","method","graph_sha256","query_sha256","builder","execution_memory_gib",
                                   "comparison_budget_gib","solver_threads","host","cpu_affinity","cpu_count","concurrent_configurations")}
        identity["raw_receipt"]=str(raw.resolve()) if raw else None
        build=dict(identity,status=row["status"],build_s=row["build_s"],
                   index_payload_bytes=row["index_payload_bytes"],process_peak_kib=row["process_peak_kib"])
        query=dict(identity,status="verified" if row["status"]=="verified" else "not_run",
                   expected=row["expected"],checked=row["checked"],mismatches=row["mismatches"],
                   batch_s=row["batch_s"],mean_us=row["mean_us"],
                   answers="answers.tsv" if answer else None)
        if answer:
            path=target/"answers.tsv"
            link=os.path.relpath(answer,target)
            if not path.exists():
                path.symlink_to(link)
            elif path.resolve()!=answer.resolve():
                raise ValueError(f"{path}: answer link differs")
        for name,value in (("build.json",build),("query.json",query)):
            path=target/name
            tmp=path.with_suffix(".part")
            tmp.write_text(json.dumps(value,indent=2)+"\n")
            tmp.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs",type=Path,nargs="+")
    parser.add_argument("--output",type=Path,help="merged performance.tsv path for multiple disjoint runs")
    args=parser.parse_args()
    if len(args.runs)>1 and not args.output:
        parser.error("multiple runs require --output")
    rows=[]
    graphs=set()
    source_runs={}
    protocol=None
    for run in args.runs:
        config=load(run/"run.json")
        source_runs[run.name]=run
        common=tuple(config.get(k) for k in
            ("host","compiler","query_name","b","d2_cap","memory_gib","kreach_memory_gib","timeout","fixed_k","cpu_affinity","solver_threads"))
        if protocol is None:
            protocol=common
        elif common!=protocol:
            raise ValueError("merged runs use different configurations")
        if graphs & set(config["graphs"]):
            raise ValueError("merged runs contain overlapping graphs")
        graphs.update(config["graphs"])
        records_for_run=[r for graph in config["graphs"] for r in records(run,graph,config)]
        write_table(run/"performance.tsv",records_for_run)
        write_method_results(run,records_for_run)
        rows.extend(dict(r,run=run.name,git_revision=config.get("git_revision",""),
                         b=config.get("b",""),d2_cap=config.get("d2_cap","")) for r in records_for_run)
        print(run,dict(Counter(r["status"] for r in records_for_run)),flush=True)
    if args.output:
        write_table(args.output,rows)
        write_method_results(args.output.parent,rows,source_runs=source_runs)
    counts=Counter(r["status"] for r in rows)
    if counts["invalid"] or counts["mismatch"]:
        raise SystemExit("a correctness check failed")


if __name__=="__main__":
    main()
