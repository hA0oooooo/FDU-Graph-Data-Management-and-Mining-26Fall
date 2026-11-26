"""Retry resource-limited exact baselines at larger, serial memory budgets."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

from radius.run import ROOT, WORKLOADS, digest, read_rows
from workload import workload_spec


def load(path):
    return json.loads(path.read_text())


def save(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".part")
    tmp.write_text(json.dumps(data,indent=2)+"\n")
    tmp.replace(path)


def meminfo():
    fields={}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key,value=line.split(":",1)
        if key in ("MemTotal","MemAvailable"):
            fields[key]=int(value.split()[0])*1024
    return fields


def budget_wait(gib,reserve):
    while meminfo()["MemAvailable"]<(gib+reserve)*2**30:
        time.sleep(60)


def lower_bounds(prior):
    result={}
    for name in ("kreach-capacity.tsv",):
        path=prior.parent/name
        if path.exists():
            for r in read_rows(path):
                result[(r["graph"],f"kreach-{r['k']}")]=int(r["payload_lower_bytes"])
    return result


def target_for(root, graph, method, gib):
    if method.startswith("kreach-"):
        family,k=method.rsplit("-",1)
        return root/"methods"/family/graph/("k"+k)/(f"memory-{gib}GiB")
    return root/"methods"/method/graph/(f"memory-{gib}GiB")


def receipt_for(target, graph, method):
    if method.startswith("kreach-"):
        return target/"receipt.json"
    return target/"raw"/graph/(method+".json")


def run_attempt(root, graph, method, gib, spec, cpus, build_threads, query_name, review=False):
    target=target_for(root,graph,method,gib)
    receipt=receipt_for(target,graph,method)
    if review and not receipt.exists():
        raise FileNotFoundError(receipt)
    target.mkdir(parents=True,exist_ok=True)
    edges=ROOT/"dataset/prepared"/(graph+".edges")
    work=WORKLOADS/graph
    manifest,query=workload_spec(work,query_name)
    query_path=work/query_name
    if digest(edges)!=manifest["graph_sha256"] or digest(query_path)!=query["sha256"]:
        raise ValueError(f"{graph}: frozen input mismatch")
    if method.startswith("kreach-"):
        k=int(method.rsplit("-",1)[1])
        command=[sys.executable,ROOT/"src/baselines/historical.py","--graph",graph,"--nodes",str(spec["nodes"]),
                 "--edges",str(spec["edges"]),"--query-name",query_name,"--methods","kreach","--k",str(k),
                 "--memory-gib",str(gib),"--output",receipt,"--answers-dir",target/"answers"]
        expected=sum(int(r["k"])==k for r in read_rows(query_path))
        builder="scalar"; threads=1
    else:
        command=[sys.executable,ROOT/"src/baselines/cover/matrix.py",graph,"--methods",method,
                 "--builder","packed","--build-threads",str(build_threads),
                 "--memory-mib",str(gib*1024),"--query-name",query_name,"--output",target/"raw"]
        expected=query["queries"]
        builder="packed"; threads=build_threads
    if not receipt.exists():
        with (target/"driver.log").open("a") as log:
            subprocess.run(["taskset","-c",cpus,*map(str,command)],cwd=ROOT,
                           stdout=log,stderr=subprocess.STDOUT,check=True)
    raw=load(receipt)
    if method.startswith("kreach-"):
        r=raw["kreach"][0]
        status=r["status"]
        if "bad_alloc" in r.get("detail",""): status="allocation_failed"
        checked=r.get("queries"); errors=r.get("mismatches")
        build=r.get("build_ns"); first_ns=r.get("first_batch_ns")
        query_ns=r.get("median_batch_ns",first_ns) if r.get("query_repeats") else first_ns
        size=r.get("index_bytes")
        hashes=(raw["graph_sha256"],raw["test_sha256"])
        answers=target/"answers"/(method+".tsv")
    else:
        r=raw["results"][0]; status=r["status"]
        classes=r.get("by_class")
        checked=sum(c["n"] for c in classes.values()) if classes else None
        errors=sum(c["mismatches"] for c in classes.values()) if classes else None
        build=r.get("build_ns"); first_ns=r.get("query_ns")
        query_ns=r.get("median_query_ns",first_ns) if r.get("query_repeats") else first_ns
        size=r.get("encoded_bytes")
        hashes=(raw["edges_sha256"],raw["queries_sha256"])
        answers=receipt.with_suffix(".answers.tsv")
    if hashes!=(manifest["graph_sha256"],query["sha256"]):
        raise ValueError(f"{receipt}: input hashes differ")
    valid=status in ("ok","passed","verified") and checked==expected and errors==0
    if valid and answers.exists():
        truth=[str(int(0<=int(q["d"])<=int(q["k"]))) for q in read_rows(query_path)
               if not method.startswith("kreach-") or int(q["k"])==k]
        predictions=[a["answer"] for a in read_rows(answers)]
        valid=predictions==truth
    if status in ("ok","passed","verified"):
        status="verified" if valid else "mismatch"
    row=dict(graph=graph,method=method,status=status,expected=expected,
             checked=checked if valid else None,mismatches=errors if valid else None,
             build_s=build/1e9 if valid else None,batch_s=query_ns/1e9 if valid else None,
             mean_us=query_ns/1000/expected if valid else None,
             first_batch_s=first_ns/1e9 if valid else None,
             query_repeats=r.get("query_repeats") if valid else None,
             timing_protocol=("warmup_median" if r.get("query_repeats") else "first_batch") if valid else None,
             index_payload_bytes=size if valid else None,
             index_allocated_bytes=r.get("index_allocated_bytes") if valid else None,
             ready_rss_kib=r.get("ready_rss_kib") if valid else None,
             process_peak_kib=r.get("process_peak_kib") if valid else None,
             query_sha256=query["sha256"],graph_sha256=manifest["graph_sha256"],receipt=str(receipt.relative_to(root)),
             answers=str(answers.relative_to(root)) if answers.exists() else None,
             builder=builder,build_threads=threads,execution_memory_gib=gib,comparison_budget_gib=gib,
             solver_threads=1,host=socket.gethostname(),cpu_affinity=cpus,
             cpu_count=len(parse_cpus(cpus)),concurrent_configurations=1)
    if not review:
        save(target/"build.json",row)
        save(target/"query.json",{k:row[k] for k in ("graph","method","status","expected","checked","mismatches","batch_s","first_batch_s","query_repeats","timing_protocol","mean_us","answers","query_sha256")})
    return row


def parse_cpus(text):
    cpus=[]
    for part in text.split(","):
        if "-" in part:
            a,b=map(int,part.split("-"))
            cpus.extend(range(a,b+1))
        else:
            cpus.append(int(part))
    return cpus


def write_table(path,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for row in rows for k in row))
    tmp=path.with_suffix(".part")
    with tmp.open("w") as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter="\t",lineterminator="\n")
        w.writeheader();w.writerows(rows)
    tmp.replace(path)


def review_run(root, meta):
    info=load(root/"run.json")
    results=[]; attempts=[]
    for job in info["jobs"]:
        graph,method=job["graph"],job["method"]
        bound=job.get("lower_bytes") or 0
        if bound>info["physical_memory_bytes"]:
            results.append(dict(graph=graph,method=method,status="physical_capacity_proved",
                                lower_bytes=bound,physical_memory_bytes=info["physical_memory_bytes"]))
            continue
        row=dict(graph=graph,method=method,status="pending")
        for gib in info["budgets"]:
            target=target_for(root,graph,method,gib)
            if not receipt_for(target,graph,method).exists():
                if (target/"driver.log").exists():
                    row=dict(graph=graph,method=method,status="started_without_receipt",execution_memory_gib=gib)
                continue
            row=run_attempt(root,graph,method,gib,meta[graph],info["cpu_set"],info["build_threads"],info["query_name"],review=True)
            attempts.append(row)
            if row["status"]=="verified":
                break
        results.append(row)
    write_table(root/"reviewed_performance.tsv",results)
    write_table(root/"reviewed_attempts.tsv",attempts)
    print(dict(Counter(r["status"] for r in results)))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("prior",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--budgets",nargs="+",type=int,default=[256,384,448])
    ap.add_argument("--cpu-set",default="24-31")
    ap.add_argument("--build-threads",type=int,default=8)
    ap.add_argument("--reserve-gib",type=int,default=32,help="leave shared-host memory available")
    ap.add_argument("--query-name",default="benchmark.tsv")
    ap.add_argument("--review",action="store_true",help="rebuild reviewed data from available receipts without starting work")
    args=ap.parse_args()
    args.output=args.output.resolve()
    args.output.mkdir(parents=True,exist_ok=True)
    meta=load(ROOT/"dataset/manifest.json")|load(ROOT/"dataset/catalogue.json")|load(ROOT/"dataset/synthetic.json")
    if args.review:
        review_run(args.output,meta)
        return
    prior=read_rows(args.prior)
    lower=lower_bounds(args.prior)
    total=meminfo()["MemTotal"]
    jobs=[(r["graph"],r["method"]) for r in prior if r["status"] in ("capacity_proved","allocation_failed")
          and (r["method"].startswith("kreach-") or r["method"] in ("vcrea","vcrea-plus","pll"))]
    jobs.sort(key=lambda j:(j[1].startswith("kreach-"),meta[j[0]]["edges"],j[1]))
    attempts=[];results=[]
    save(args.output/"run.json",dict(source=str(args.prior.resolve()),query_name=args.query_name,
         budgets=args.budgets,cpu_set=args.cpu_set,build_threads=args.build_threads,host=socket.gethostname(),
         physical_memory_bytes=total,jobs=[dict(graph=g,method=m,lower_bytes=lower.get((g,m))) for g,m in jobs]))
    for graph,method in jobs:
        bound=lower.get((graph,method),0)
        if bound>total:
            results.append(dict(graph=graph,method=method,status="physical_capacity_proved",
                                lower_bytes=bound,physical_memory_bytes=total))
            write_table(args.output/"performance.tsv",results)
            print(graph,method,"physical capacity lower bound",round(bound/2**30,2),flush=True)
            continue
        options=[b for b in sorted(set(args.budgets)) if b*2**30>bound and (b+args.reserve_gib)*2**30<=total]
        if not options:
            raise RuntimeError(f"{graph} {method}: no feasible budget")
        for gib in options:
            if not receipt_for(target_for(args.output,graph,method,gib),graph,method).exists():
                print(graph,method,"waiting for",gib,"GiB",flush=True)
                budget_wait(gib,args.reserve_gib)
                print(graph,method,"running",gib,"GiB",flush=True)
            row=run_attempt(args.output,graph,method,gib,meta[graph],args.cpu_set,args.build_threads,args.query_name)
            attempts.append(row)
            write_table(args.output/"attempts.tsv",attempts)
            print(graph,method,gib,row["status"],flush=True)
            if row["status"]=="verified": break
            if row["status"]!="allocation_failed":
                raise RuntimeError(f"unexpected stress status: {row}")
        results.append(row)
        write_table(args.output/"performance.tsv",results)
    print("expanded stress attempts complete",flush=True)


if __name__=="__main__":
    main()
