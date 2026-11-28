"""Run mechanism ablations with frozen radii and join the verified historical baselines."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from hotspot import ROOT, compile_tool, digest, inputs, read_rows, write_rows
from workload import fixed_queries, workload_spec


def analyze(main):
    protocol=json.loads((main/"protocol.json").read_text())
    if protocol.get("fixed_k") is not None:
        raise ValueError("mechanism groups expect a mixed-k primary workload")
    frozen=json.loads((main/"frozen.json").read_text())
    historical=ROOT/"output/baselines"
    ranks=read_rows(historical/"ranking/metrics.tsv")
    receipts=read_rows(historical/"performance.tsv")
    cpu=protocol["cpu"]
    os.sched_setaffinity(0,{cpu})
    os.environ["KHOP_QUERY_REPEATS"]="5"
    binary=compile_tool("hotspot_ablation")
    out=main/"ablation"
    out.mkdir(exist_ok=True)
    identity=dict(primary_freeze=digest(main/"frozen.json"),
        binary_sha256=digest(binary),cpu=cpu,memory_gib=48,threads=1,
        protocol="sequential methods in shared diagnostic process; warm-up plus five timed batches")
    receipt=out/"protocol.json"
    if receipt.exists() and json.loads(receipt.read_text())!=identity:
        raise ValueError("different ablation inputs at destination")
    receipt.write_text(json.dumps(identity,indent=2)+"\n")
    times,mechanism,reference=[],[],[]
    for graph in protocol["graphs"]:
        work,edges,spec,hashes=inputs(graph)
        n=spec["nodes"]; config=frozen[graph]
        if hashes!=config["splits"] or spec["graph_sha256"]!=config["graph_sha256"]:
            raise ValueError("different frozen inputs")
        for m,h in config["configurations"].items():
            if digest(main/graph/m/"radii.tsv")!=h: raise ValueError("frozen radii changed")
        splits=("benchmark","benchmark-uniform","benchmark-stratified","test")
        for split in splits:
            _,record=workload_spec(work,split+".tsv")
            if record["sha256"]!=digest(work/(split+".tsv")): raise ValueError("frozen split changed")
        source_sets=[{q["s"] for q in read_rows(work/(s+".tsv"))}
                     for s in ("train","validation","test","benchmark")]
        if any(a & b for i,a in enumerate(source_sets) for b in source_sets[i+1:]):
            raise ValueError("overlapping source groups")
        dest=out/graph; dest.mkdir(exist_ok=True)
        mem=48*2**30
        if not (dest/"mechanism.tsv").exists():
            with tempfile.TemporaryDirectory(dir=dest) as tmp:
                pending = Path(tmp)
                subprocess.run(["prlimit",f"--as={mem}:{mem}","--","/usr/bin/time","-f","%M","-o",pending/"peak_kib.txt",
                                binary,str(n),edges,work,main/graph,pending],check=True)
                for name in ("peak_kib.txt", "timing.tsv", "mechanism.tsv"):
                    (pending/name).replace(dest/name)
        counts={split: int(workload_spec(work,split+".tsv")[1]["queries"]) for split in splits}
        timings=read_rows(dest/"timing.tsv"); details=read_rows(dest/"mechanism.tsv")
        methods={"bibfs","tree","uniform","adaptive","positive-only","tree-uniform","tree-adaptive"}
        if len(timings)!=len(splits)*len(methods) or {(r["split"],r["method"]) for r in timings}!={(s,m) for s in splits for m in methods}:
            raise ValueError("incomplete diagnostic timing")
        if any(int(r["queries"])!=counts[r["split"]] or int(r["repeats"])!=5 for r in timings):
            raise ValueError("wrong diagnostic batch size")
        if any(sum(int(r["queries"]) for r in details if r["split"]==s)!=nq for s,nq in counts.items()):
            raise ValueError("incomplete diagnostic classification")
        fit={m:float(read_rows(main/graph/m/"fit.tsv")[0]["build_s"]) for m in ("uniform","adaptive")}
        for row in read_rows(dest/"timing.tsv"):
            method=row["method"]; mean=int(row["batch_ns"])/int(row["queries"])/1000
            training=(fit["uniform"] if "uniform" in method else fit["adaptive"]
                      if method in ("adaptive","tree-adaptive","positive-only") else 0)
            build=training+float(row["tree_build_s"])
            times.append(dict(graph=graph,**row,mean_us=mean,cost_1m_s=build+mean,
                              within_budget=int(row["aux_bytes"])<=protocol["bytes_per_vertex"]*n))
        mechanism.extend(dict(graph=graph,**row) for row in read_rows(dest/"mechanism.tsv"))
        # In the mixed ranking fixed-k methods aggregate all three partitions.
        expected={str(k):hashlib.sha256(fixed_queries(work/"benchmark.tsv",k)[0].encode()).hexdigest()
                  for k in (2,4,6)}
        per_graph=[r for r in receipts if r["graph"]==graph]
        if not per_graph: raise ValueError("missing historical results")
        for row in per_graph:
            if (row["graph_sha256"]!=config["graph_sha256"] or
                row["query_sha256"] not in {hashes["benchmark"],*expected.values()} or
                row["status"]!="verified" or row["cpu_affinity"]!=str(cpu) or
                float(row["execution_memory_gib"])!=48 or int(row["query_repeats"])!=5 or
                int(row["build_threads"])!=1 or int(row["solver_threads"])!=1):
                raise ValueError("historical comparison protocol differs")
        benchmark=read_rows(work/"benchmark.tsv")
        for method in ("kreach","scalable"):
            group={r["method"]:r for r in per_graph if r["method"].rsplit("-",1)[0]==method}
            for k in (2,4,6):
                row=group[f"{method}-{k}"]
                qs=[q for q in benchmark if int(q["k"])==k]
                answers=read_rows(historical/"runs"/row["run"]/row["answers"])
                if (row["query_sha256"] not in (hashes["benchmark"],expected[str(k)]) or
                    len(qs)!=int(row["checked"]) or
                    [int(a["answer"]) for a in answers]!=[0<=int(q["d"])<=k for q in qs]):
                    raise ValueError(f"{graph} {method}: fixed-k answers differ")
        reference.extend(r for r in ranks if r["graph"]==graph and r["status"]=="verified")
    write_rows(out/"timing.tsv",times)
    write_rows(out/"mechanism.tsv",mechanism)
    write_rows(out/"historical.tsv",reference)


def construction(main):
    protocol = json.loads((main / "protocol.json").read_text())
    if protocol.get("fixed_k") is not None or protocol.get("root_pool", "trace") != "trace":
        raise ValueError("construction diagnostic expects mixed-k trace-selected roots")
    cpu = protocol["cpu"]
    os.sched_setaffinity(0, {cpu})
    mem = protocol["memory_gib"] * 2**30
    binary = compile_tool("hotspot_diagnostics")
    frozen = json.loads((main / "frozen.json").read_text())
    out = main / "ablation"
    (out / "frontier").mkdir(parents=True, exist_ok=True)
    totals = []
    for graph, config in frozen.items():
        work, edges, spec, hashes = inputs(graph)
        radii = main / graph / "adaptive/radii.tsv"
        if (hashes != config["splits"] or spec["graph_sha256"] != config["graph_sha256"] or
                digest(radii) != config["configurations"]["adaptive"]):
            raise ValueError("frozen inputs or radii changed")
        dest = out / graph
        dest.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=dest) as tmp:
            costs, frontier = Path(tmp)/"construction.tsv", Path(tmp)/"frontier.tsv"
            with frontier.open("w") as stream:
                subprocess.run(["prlimit", f"--as={mem}:{mem}", "--", binary, str(config["n"]),
                                edges, work, radii, costs], stdout=stream, check=True)
            rows = read_rows(costs)
            totals.append(dict(graph=graph, directions=len(rows), **{
                key: sum(int(r[key]) for r in rows) for key in
                ("full_scans", "global_cap_scans", "demand_cap_scans", "chosen_scans")}))
            costs.replace(dest/"construction.tsv")
            frontier.replace(out/"frontier"/(graph+".tsv"))
    write_rows(out/"construction.tsv", totals)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main",nargs="?",type=Path,default=ROOT/"output/adaptive-radius/hotspot")
    parser.add_argument("--construction", action="store_true", help="rebuild directional profiles to their training demand")
    args = parser.parse_args()
    (construction if args.construction else analyze)(args.main)
