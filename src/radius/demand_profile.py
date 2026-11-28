"""Frozen paired demand-profile experiment with independent construction repetitions."""
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess

from hotspot import GRAPHS, ROOT, compile_tool, digest, inputs, read_rows, write_rows
from workload import fixed_queries

METHODS = ("bibfs", "adaptive-full", "adaptive-global", "adaptive-demand", "uniform-global")
BUILDERS = METHODS[1:4]
TRANSFER_GRAPH = "email-EuAll"
SEED = 43019
CPU = 46
MEMORY = 48
PAIRS = 5
OLD = ROOT / "output/adaptive-radius/hotspot"
EMPTY = hashlib.sha256(b"").hexdigest()


def json_file(path, value):
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError(f"frozen protocol or configuration changed: {path}")
    else:
        tmp = path.with_suffix(".part")
        tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        tmp.replace(path)


def read_one(path):
    rows = read_rows(path)
    if len(rows) != 1:
        raise ValueError(f"expected one result: {path}")
    return rows[0]


def checked_process(binary, dest, args, identity, files):
    """One independent restricted process; retain failures and verify completed receipts."""
    receipt = dest / "receipt.json"
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        if saved["identity"] != identity or any(digest(dest/f) != h for f,h in saved["files"].items()):
            raise ValueError(f"completed receipt changed: {dest}")
        return saved
    if dest.exists():
        raise ValueError(f"incomplete process directory needs review: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    pending = dest.with_name(dest.name + ".pending")
    if pending.exists():
        raise ValueError(f"incomplete process directory needs review: {pending}")
    pending.mkdir()
    memory=MEMORY * 2**30
    command = ["prlimit",f"--as={memory}:{memory}","--","/usr/bin/time","-f","%M",
               "-o",pending/"peak_kib.txt",binary,*[pending if a is None else a for a in args]]
    with (pending/"stderr.txt").open("w") as log:
        subprocess.run(command,stderr=log,check=True)
    table = pending/"table.bin"
    table_hash = digest(table) if table.exists() else EMPTY
    if table.exists():
        table.unlink()
    result = dict(identity=identity,table_sha256=table_hash,
                  files={f:digest(pending/f) for f in (*files,"peak_kib.txt")})
    json_file(pending/"receipt.json",result)
    pending.rename(dest)
    return result


def fit(binary, dest, method, graph, n, edges, work, hashes, fixed, config=None):
    identity = dict(graph=graph,method=method,inputs=hashes,fixed=fixed,
                    config=digest(config) if config else None)
    if method == "bibfs":
        return dict(build_s=0.,index_bytes=0,candidates=0,training_s=0.,probe_s=0.,
                    choose_s=0.,validation_s=0.,encode_s=0.,probe_scans=0,
                    build_peak_kib=0,config_sha256=EMPTY,table_sha256=EMPTY,candidate_sha256=EMPTY)
    phase = "study-build" if config else "study-fit"
    result = checked_process(binary,dest,[phase,method,str(n),edges,work,None,config or "-",
                            str(4*n),str(fixed or -1),"trace"],identity,
                            ("fit.tsv","radii.tsv","candidates.tsv","directions.tsv","validation.tsv"))
    row=read_one(dest/"fit.tsv")
    fitted={k:float(v) if k.endswith("_s") else int(v) for k,v in row.items()}
    if fitted["index_bytes"]>4*n:
        raise ValueError("index budget exceeded")
    return dict(**fitted,build_peak_kib=int((dest/"peak_kib.txt").read_text()),
                config_sha256=digest(dest/"radii.tsv"),table_sha256=result["table_sha256"],
                candidate_sha256=digest(dest/"candidates.tsv"))


def evaluate(binary,dest,method,graph,n,edges,query,fit_dir,built,fixed=None,transfer=False):
    config=fit_dir/"radii.tsv" if method!="bibfs" else "-"
    if method!="bibfs" and digest(config)!=built["config_sha256"]:
        raise ValueError("frozen configuration changed")
    qhash=digest(query)
    identity=dict(graph=graph,method=method,query=qhash,config=built["config_sha256"],
                  table=built["table_sha256"])
    phase="study-transfer" if transfer else "study-eval"
    result=checked_process(binary,dest,[phase,method,str(n),edges,query,None,config,
                              str(4*n),str(fixed or -1),"trace"],identity,
                              ("query.tsv","answers.tsv","details.tsv","groups.tsv")+
                              (("threshold.tsv",) if transfer else ()))
    row=read_one(dest/"query.tsv")
    truth=read_rows(query)
    if fixed is not None:
        truth=[q for q in truth if int(q["k"])==fixed]
    expected=[int(0<=int(q["d"])<=int(q["k"])) for q in truth]
    actual=[int(q["yes"]) for q in read_rows(dest/"answers.tsv")]
    detail=read_rows(dest/"details.tsv")
    if actual!=expected or [int(x["yes"]) for x in detail]!=expected:
        raise ValueError(f"wrong answer: {dest}")
    if int(row["queries"])!=len(truth) or int(row["repeats"])!=5 or sum(int(x["scans"]) for x in detail)!=int(row["scans"]):
        raise ValueError("invalid query receipt")
    if int(row["index_bytes"])!=built["index_bytes"] or result["table_sha256"]!=built["table_sha256"]:
        raise ValueError("reconstructed table differs from built table")
    groups=read_rows(dest/"groups.tsv")
    if len(groups)!=9 or sum(int(x["queries"]) for x in groups)!=len(truth) or sum(int(x["scans"]) for x in groups)!=int(row["scans"]):
        raise ValueError("wrong group accounting")
    query_us=int(row["batch_ns"])/len(truth)/1000
    build=built["build_s"]
    return dict(queries=len(truth),sources=len({q["s"] for q in truth}),mismatches=0,mean_us=query_us,
                batch_ns=int(row["batch_ns"]),scans=int(row["scans"]),certified_true=int(row["certified_true"]),
                query_peak_kib=int((dest/"peak_kib.txt").read_text()),restore_s=float(row["setup_s"]),
                cost_batch_s=build+len(truth)*query_us/1e6,cost_1m_s=build+query_us,
                cost_1b_s=build+query_us*1000,
                cold_cost_1m_s=build+float(row["setup_s"])+query_us,
                query_sha256=qhash,details_sha256=digest(dest/"details.tsv"))


def rotate(methods,pair):
    i=(pair-1)%len(methods)
    return methods[i:]+methods[:i]


def graph_inputs(graph, fixed=None):
    work,edges,spec,hashes=inputs(graph)
    # Hash filtered files so comparisons cannot accidentally use the mixed workload.
    if fixed:
        hashes = {s:hashlib.sha256(fixed_queries(work/(s+".tsv"),fixed)[0].encode()).hexdigest()
                  for s in hashes}
    return work,edges,spec["nodes"],dict(graph_sha256=spec["graph_sha256"],**hashes)


def fresh_workloads(out, work, edges, n, graph_hash):
    dest=out/"workloads"/TRANSFER_GRAPH
    dest.mkdir(parents=True,exist_ok=True)
    exclude=set()
    for p in work.rglob("*.tsv"):
        rows=read_rows(p)
        if rows and "s" in rows[0]:
            exclude.update(int(q["s"]) for q in rows)
    prior=work/"prior-sources.txt"
    if prior.exists():
        exclude.update(map(int,prior.read_text().split()))
    exclusion=dest/"excluded.txt"
    body="".join(f"{s}\n" for s in sorted(exclude))
    if exclusion.exists() and exclusion.read_text()!=body:
        raise ValueError("holdout exclusion changed")
    exclusion.write_text(body)
    split_names=("holdout-1","holdout-2","holdout-3")
    if not (dest/"manifest.json").exists():
        if any((dest/(s+".tsv")).exists() for s in split_names):
            raise ValueError("partial holdout generation")
        subprocess.run([compile_tool("workloads"),str(n),edges,exclusion,dest,"confirm",str(SEED)],check=True)
    data=dict(seed=SEED,graph_sha256=graph_hash,exclusion_sha256=digest(exclusion),splits={})
    for name in split_names:
        path=dest/(name+".tsv")
        rows=read_rows(path)
        sources={int(r["s"]) for r in rows}
        if not rows or sources & exclude:
            raise ValueError("new source partition is empty or overlaps")
        exclude.update(sources)
        classes={label:0 for label in ("within","beyond","unreachable")}
        for q in rows:
            d,k=int(q["d"]),int(q["k"])
            classes["unreachable" if d<0 else "beyond" if d>k else "within"]+=1
        data["splits"][name]=dict(sha256=digest(path),queries=len(rows),sources=len(sources),**classes)
    json_file(dest/"manifest.json",data)
    return dest,data


def historical(out, source):
    base=ROOT/"output/baselines"
    receipts=read_rows(base/"performance.tsv")
    ranks=read_rows(base/"ranking/metrics.tsv")
    rows=[]
    for graph in (*GRAPHS,TRANSFER_GRAPH):
        work,_,n,hashes=source[(graph,None)]
        benchmark=read_rows(work/"benchmark.tsv")
        expected={str(k):hashlib.sha256(fixed_queries(work/"benchmark.tsv",k)[0].encode()).hexdigest()
                  for k in (2,4,6)}
        selected=[r for r in receipts if r["graph"]==graph]
        for r in selected:
            assert r["status"]=="verified" and int(r["mismatches"])==0
            assert r["graph_sha256"]==hashes["graph_sha256"] and r["cpu_affinity"]==str(CPU)
            assert float(r["execution_memory_gib"])==MEMORY and r["build_threads"]==r["solver_threads"]=="1"
            assert r["query_repeats"]=="5" and r["timing_protocol"]=="warmup_median"
            assert r["host"]==os.uname().nodename
            partition=r["method"].rsplit("-",1)[-1]
            queries=[q for q in benchmark if q["k"]==partition] if partition in expected else benchmark
            target=expected.get(partition,hashes["benchmark"])
            assert r["query_sha256"] in {target,hashes["benchmark"]} and len(queries)==int(r["checked"])
            answers=read_rows(base/"runs"/r["run"]/r["answers"])
            assert [int(a["answer"]) for a in answers]==[int(0<=int(q["d"])<=int(q["k"])) for q in queries]
        matches=[r for r in ranks if r["graph"]==graph and r["status"]=="verified"]
        assert len(matches)==9
        rows.extend(dict(**r,within_budget=float(r["index_allocated_bytes"])<=4*n,
                         graph_sha256=hashes["graph_sha256"],query_sha256=hashes["benchmark"])
                    for r in matches)
    write_rows(out/"historical.tsv",rows)


def summarize(out, main, construction, transfer):
    med=statistics.median
    result=[]
    for graph,load in dict.fromkeys((r["graph"],r["load"]) for r in main):
        rows=[r for r in main if (r["graph"],r["load"])==(graph,load)]
        for method in METHODS:
            group=[r for r in rows if r["method"]==method]
            assert len(group)==PAIRS
            rec=dict(graph=graph,load=load,method=method,pairs=len(group))
            for key in ("build_s","probe_s","probe_scans","mean_us","index_bytes","cost_1m_s","cost_1b_s","cold_cost_1m_s","scans","build_peak_kib","query_peak_kib"):
                rec[key]=med(r[key] for r in group)
            base={r["pair"]:r for r in rows if r["method"]=="bibfs"}
            breaks=[1e6*r["build_s"]/(base[r["pair"]]["mean_us"]-r["mean_us"]) for r in group
                    if r["mean_us"]<base[r["pair"]]["mean_us"]]
            rec["break_even_queries"]=med(breaks) if len(breaks)==PAIRS else "NA"
            result.append(rec)
    write_rows(out/"summary.tsv",result)
    paired=[]
    def compare(rows,group,old,new,metric):
        a={r["pair"]:r[metric] for r in rows if r["method"]==old}
        b={r["pair"]:r[metric] for r in rows if r["method"]==new}
        assert a.keys()==b.keys() and len(a)==PAIRS
        ratios=[1-b[i]/a[i] for i in a if a[i]>0]
        valid=len(ratios)==PAIRS
        paired.append(dict(group=group,reference=old,candidate=new,metric=metric,valid_pairs=len(ratios),
                           median=med(ratios) if ratios else "NA",minimum=min(ratios) if ratios else "NA",
                           maximum=max(ratios) if ratios else "NA",positive=sum(x>0 for x in ratios),
                           stable=valid and med(ratios)>=.05 and sum(x>0 for x in ratios)>=4))
    for graph in GRAPHS:
        rows=[r for r in construction if r["graph"]==graph]
        for ref in ("adaptive-full","adaptive-global"):
            for metric in ("probe_scans","probe_s","build_s"):
                compare(rows,"fixed:"+graph,ref,"adaptive-demand",metric)
    for graph,load in dict.fromkeys((r["graph"],r["load"]) for r in main):
        rows=[r for r in main if (r["graph"],r["load"])==(graph,load)]
        for ref in ("bibfs","adaptive-global","uniform-global"):
            for metric in ("build_s","mean_us","cost_1m_s"):
                compare(rows,load+":"+graph,ref,"adaptive-demand",metric)
    merged=[]
    for pair in range(1,PAIRS+1):
        for method in METHODS:
            rows=[r for r in transfer if r["pair"]==pair and r["method"]==method]
            assert len(rows)==3
            assert len({r["config_sha256"] for r in rows})==1
            nq=sum(r["queries"] for r in rows)
            t=sum(r["batch_ns"] for r in rows)/nq/1000
            b=rows[0]["build_s"]
            weighted=[]
            for k,w in ((2,.1),(4,.2),(6,.7)):
                count=sum(r[f"k{k}_queries"] for r in rows)
                if count:
                    weighted.append(w*sum(r[f"k{k}_batch_ns"] for r in rows if r[f"k{k}_queries"])/count/1000)
            merged.append(dict(pair=pair,method=method,queries=nq,build_s=b,mean_us=t,
                               cost_1m_s=b+t,shifted_cost_1m_s=b+sum(weighted) if len(weighted)==3 else "NA"))
    write_rows(out/"transfer-combined.tsv",merged)
    for ref in ("bibfs","uniform-global"):
        compare(merged,"transfer:"+TRANSFER_GRAPH,ref,"adaptive-demand","cost_1m_s")
    write_rows(out/"paired.tsv",paired)


def experiment(out):
    os.sched_setaffinity(0,{CPU})
    os.environ["KHOP_QUERY_REPEATS"]="5"
    binary=compile_tool("hotspot")
    out=out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    units=[(graph,None) for graph in (*GRAPHS,TRANSFER_GRAPH)]+[("wiki-Vote",4)]
    source={unit:graph_inputs(*unit) for unit in units}
    inputs_meta={f"{g}/{k or 'mixed'}":v[3] for (g,k),v in source.items()}
    deps=[*sorted((ROOT/"src/radius").glob("*.hpp")),*[ROOT/"src/radius"/s for s in
          ("hotspot.cpp","hotspot.py","demand_profile.py","workloads.cpp","run.py")],
          ROOT/"src/benchmark_metrics.hpp",ROOT/"src/workload.py"]
    code=hashlib.sha256(b"".join(p.name.encode()+p.read_bytes() for p in deps)).hexdigest()
    prior=json.loads((OLD/"frozen.json").read_text())
    old_configs={g:digest(OLD/g/"adaptive/radii.tsv") for g in GRAPHS}
    assert all(old_configs[g]==prior[g]["configurations"]["adaptive"] and
               source[(g,None)][3]["graph_sha256"]==prior[g]["graph_sha256"] for g in GRAPHS)
    proto=dict(host=os.uname().nodename,cpu=CPU,threads=1,memory_gib=MEMORY,pairs=PAIRS,
               bytes_per_vertex=4,methods=METHODS,seed=SEED,inputs=inputs_meta,
               source_sha256=code,binary_sha256=digest(binary),fixed_configs=old_configs,
               benchmark="warm-up plus five timed batches; independent training each deployment")
    # JSON normalization handles tuple/list representation on resume.
    json_file(out/"protocol.json",json.loads(json.dumps(proto)))
    fixed_results=[]
    for graph in GRAPHS:
        work,edges,n,hashes=source[(graph,None)]
        configuration=OLD/graph/"adaptive/radii.tsv"
        for pair in range(1,PAIRS+1):
            for method in rotate(BUILDERS,pair):
                dest=out/"construction"/graph/method/f"pair-{pair}"
                result=fit(binary,dest,method,graph,n,edges,work,hashes,None,configuration)
                fixed_results.append(dict(graph=graph,method=method,pair=pair,**result))
        rows=[r for r in fixed_results if r["graph"]==graph]
        assert len({(r["candidate_sha256"],r["table_sha256"],r["config_sha256"],r["index_bytes"]) for r in rows})==1
        for r in rows:
            r["candidate_equivalent"]=True
        print(graph,"fixed construction verified",flush=True)
    write_rows(out/"construction.tsv",fixed_results)
    # Freeze all independent configurations before evaluating any formal query split.
    frozen={}
    for graph,k in units:
        work,edges,n,hashes=source[(graph,k)]
        load=f"k{k}" if k else "mixed"
        for pair in range(1,PAIRS+1):
            for method in rotate(METHODS,pair):
                dest=out/"deploy"/load/graph/method/f"pair-{pair}"/"fit"
                key=f"{load}/{graph}/{method}/pair-{pair}"
                frozen[key]=fit(binary,dest,method,graph,n,edges,work,hashes,k)
        for method in BUILDERS:
            assert len({frozen[f"{load}/{graph}/{method}/pair-{p}"]["candidate_sha256"] for p in range(1,PAIRS+1)})==1
        assert len({frozen[f"{load}/{graph}/{method}/pair-1"]["candidate_sha256"] for method in BUILDERS})==1
        print(graph,load,"independent fits frozen",flush=True)
    json_file(out/"frozen.json",frozen)
    # Validate query behavior on the same fixed representation across all three builders.
    for graph in GRAPHS:
        work,edges,n,_=source[(graph,None)]
        rows=[]
        for method in BUILDERS:
            dest=out/"construction"/graph/method/"pair-1"
            built=next(r for r in fixed_results if r["graph"]==graph and r["method"]==method and r["pair"]==1)
            rows.append(evaluate(binary,dest/"query",method,graph,n,edges,work/"benchmark.tsv",dest,built))
        assert len({r["details_sha256"] for r in rows})==1
    main=[]
    for graph,k in units:
        work,edges,n,hashes=source[(graph,k)]
        load=f"k{k}" if k else "mixed"
        for pair in range(1,PAIRS+1):
            for position,method in enumerate(rotate(METHODS,pair),1):
                dest=out/"deploy"/load/graph/method/f"pair-{pair}"
                built=frozen[f"{load}/{graph}/{method}/pair-{pair}"]
                measured=evaluate(binary,dest/"query",method,graph,n,edges,work/"benchmark.tsv",dest/"fit",built,k)
                measured["query_sha256"]=hashes["benchmark"]
                main.append(dict(graph=graph,load=load,method=method,pair=pair,position=position,
                                 graph_sha256=hashes["graph_sha256"],**built,**measured))
        write_rows(out/"main.tsv",main)
        print(graph,load,"formal queries verified",flush=True)
    work,edges,n,hashes=source[(TRANSFER_GRAPH,None)]
    folder,meta=fresh_workloads(out,work,edges,n,hashes["graph_sha256"])
    transfer=[]
    for split in meta["splits"]:
        path=folder/(split+".tsv")
        for pair in range(1,PAIRS+1):
            for method in rotate(METHODS,pair):
                base=out/"deploy/mixed"/TRANSFER_GRAPH/method/f"pair-{pair}"
                built=frozen[f"mixed/{TRANSFER_GRAPH}/{method}/pair-{pair}"]
                dest=out/"transfer"/split/method/f"pair-{pair}"
                measured=evaluate(binary,dest,method,TRANSFER_GRAPH,n,edges,path,base/"fit",built,transfer=True)
                extra={}
                groups=read_rows(dest/"groups.tsv")
                for name in ("within","beyond","unreachable"):
                    extra[name]=sum(int(r["queries"]) for r in groups if r["class"]==name)
                for row in read_rows(dest/"threshold.tsv"):
                    k=row["k"]; extra[f"k{k}_queries"]=int(row["queries"])
                    extra[f"k{k}_batch_ns"]=int(row["batch_ns"]) if row["batch_ns"]!="NA" else "NA"
                transfer.append(dict(graph=TRANSFER_GRAPH,split=split,method=method,pair=pair,**built,**measured,**extra))
        write_rows(out/"transfer.tsv",transfer)
        print(split,"new sources verified",flush=True)
    assert len(main)==200 and len(fixed_results)==90 and len(transfer)==75
    historical(out,source)
    summarize(out,main,fixed_results,transfer)
    print("Verified 90 fixed constructions, 200 independent deployments, 75 transfer evaluations",flush=True)
