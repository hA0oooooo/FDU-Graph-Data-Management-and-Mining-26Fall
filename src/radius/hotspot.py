"""Train, freeze and compare hotspot radii on the existing directed K-hop workloads."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from statistics import median
import subprocess

from run import ROOT, compile_tool, digest, read_rows

from workload import fixed_queries

GRAPHS = ("wiki-Vote", "web-BerkStan", "web-Google", "wiki-Talk", "p2p-Gnutella31", "ER-2048-dense")
METHODS = ("bibfs", "uniform", "adaptive", "tree", "entry")


def write_rows(path, rows):
    with path.open("w") as stream:
        writer = csv.DictWriter(stream, rows[0], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def call(binary, phase, method, n, edges, work, dest, config, cap, fixed_k, pool):
    dest.mkdir(parents=True, exist_ok=True)
    memory = 48 * 2**30
    subprocess.run(["prlimit", f"--as={memory}:{memory}", "--", "/usr/bin/time", "-f", "%M",
                    "-o", dest/"peak_kib.txt", binary, phase, method, str(n), edges, work, dest,
                    config, str(cap), str(fixed_k or -1), pool], check=True)


def inputs(graph):
    work = ROOT/"dataset/workloads"/graph
    spec = json.loads((work/"manifest.json").read_text())
    bench = json.loads((work/"benchmark.json").read_text())
    edges = ROOT/"dataset/prepared"/(graph+".edges")
    hashes = {split: digest(work/(split+".tsv")) for split in ("train", "validation", "benchmark")}
    if (digest(edges) != spec["graph_sha256"] or bench["graph_sha256"] != spec["graph_sha256"] or
        any(hashes[s] != spec["splits"][s]["sha256"] for s in ("train","validation")) or
        hashes["benchmark"] != bench["splits"]["benchmark"]["sha256"]):
        raise ValueError(f"frozen inputs changed for {graph}")
    return work, edges, spec, hashes


def experiment(args):
    os.sched_setaffinity(0, {46})
    os.environ["KHOP_QUERY_REPEATS"] = "5"
    binary = compile_tool("hotspot")
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).resolve().parent
    deps = [source/s for s in ("graph.hpp","index.hpp","query_io.hpp","hotspot.hpp","filters.hpp",
                               "hotspot.cpp","hotspot.py","run.py")] + [source.parent/"benchmark_metrics.hpp"]
    fingerprint = hashlib.sha256(b"".join(p.name.encode()+p.read_bytes() for p in deps)).hexdigest()
    info = dict(host=os.uname().nodename, cpu=46, memory_gib=48, threads=1, pairs=args.pairs,
                fixed_k=args.fixed_k, root_pool=args.root_pool, build_policy="all candidate directions to six", bytes_per_vertex=args.bytes_per_vertex,
                benchmark="warm-up plus median of five batches", binary_sha256=digest(binary),
                source_sha256=fingerprint, graphs=args.graphs)
    (args.output/"protocol.json").write_text(json.dumps(info, indent=2)+"\n")
    frozen = {}
    for graph in args.graphs:
        work, edges, spec, hashes = inputs(graph)
        n = spec["nodes"]; cap = args.bytes_per_vertex*n
        base = args.output/graph
        print(graph, "collecting training and validation traces", flush=True)
        call(binary, "fit", "profile", n, edges, work, args.output/"diagnostics"/graph, "-", cap,args.fixed_k,args.root_pool)
        for method in ("uniform", "adaptive"):
            call(binary, "fit", method, n, edges, work, base/method, "-", cap,args.fixed_k,args.root_pool)
        if args.fixed_k:
            hashes={s:hashlib.sha256(fixed_queries(work/(s+".tsv"),args.fixed_k)[0].encode()).hexdigest() for s in hashes}
        frozen[graph] = dict(n=n, graph_sha256=spec["graph_sha256"], splits=hashes,
                             configurations={m:digest(base/m/"radii.tsv") for m in ("uniform","adaptive")})
    (args.output/"frozen.json").write_text(json.dumps(frozen, indent=2)+"\n")
    results = []
    for graph, metadata in frozen.items():
        n = metadata["n"]; cap = args.bytes_per_vertex*n
        work = ROOT/"dataset/workloads"/graph
        edges = ROOT/"dataset/prepared"/(graph+".edges")
        base = args.output/graph
        truth = [int(q["d"])>=0 and int(q["d"])<=int(q["k"]) for q in read_rows(work/"benchmark.tsv")
                 if args.fixed_k is None or int(q["k"])==args.fixed_k]
        print(graph, "evaluating frozen radii", flush=True)
        for pair in range(args.pairs):
            order = list(METHODS if pair%2==0 else reversed(METHODS))
            order = order[pair:]+order[:pair]
            for method in order:
                dest = base/method/f"pair-{pair+1}"
                fit = "adaptive" if method=="entry" else method
                config = base/fit/"radii.tsv" if fit in ("adaptive","uniform") else "-"
                if config!="-" and digest(config)!=metadata["configurations"][fit]:
                    raise ValueError("configuration changed after freezing")
                call(binary, "eval", method, n, edges, work, dest, config, cap,args.fixed_k,args.root_pool)
                record = read_rows(dest/"query.tsv")[0]
                answers = [int(x["yes"]) for x in read_rows(dest/"answers.tsv")]
                if answers != truth:
                    raise ValueError(f"{graph} {method} differs from frozen truth")
                size = int(record["index_bytes"])
                build = float(record["setup_s"])
                if fit in ("uniform","adaptive"):
                    training = read_rows(base/fit/"fit.tsv")[0]
                    build = float(training["build_s"])
                    if method=="entry":
                        # Same trained radii, separately encoded entry-only index.
                        build += float(record["setup_s"])
                    elif int(training["index_bytes"])!=size or size>cap:
                        raise ValueError("budget or frozen size mismatch")
                mean_us = int(record["batch_ns"])/len(truth)/1000
                results.append(dict(graph=graph,method=method,pair=pair+1,order=order.index(method)+1,
                                    queries=len(truth),mismatches=0,build_s=build,mean_us=mean_us,
                                    cost_1m_s=build+mean_us,index_bytes=size,
                                    budget_bytes=cap,within_budget=size<=cap,scans=int(record["scans"]),
                                    certified_true=int(record["certified_true"]),
                                    peak_eval_kib=int((dest/"peak_kib.txt").read_text()),
                                    query_sha256=metadata["splits"]["benchmark"]))
        write_rows(args.output/"performance.tsv",results)
    summary = []
    for graph in frozen:
        for method in METHODS:
            rows=[r for r in results if r["graph"]==graph and r["method"]==method]
            summary.append(dict(graph=graph,method=method,pairs=len(rows),queries=rows[0]["queries"],
                                build_s=median(r["build_s"] for r in rows),
                                mean_us=median(r["mean_us"] for r in rows),
                                cost_1m_s=median(r["cost_1m_s"] for r in rows),
                                scans=rows[0]["scans"],index_bytes=rows[0]["index_bytes"],
                                mismatches=sum(r["mismatches"] for r in rows)))
    write_rows(args.output/"summary.tsv",summary)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", choices=("demand-profile",))
    parser.add_argument("--graphs", nargs="+", default=list(GRAPHS))
    parser.add_argument("--fixed-k",type=int,choices=(2,4,6))
    parser.add_argument("--root-pool",choices=("trace","degree"),default="trace")
    parser.add_argument("--pairs", type=int, default=3)
    parser.add_argument("--bytes-per-vertex", type=int, default=4)
    parser.add_argument("--output", type=Path, default=ROOT/"output/adaptive-radius/hotspot")
    args=parser.parse_args()
    if args.pairs<1 or args.bytes_per_vertex<1:
        parser.error("pairs and byte budget must be positive")
    if args.study:
        from demand_profile import experiment as demand_profile
        destination = args.output
        if destination == ROOT/"output/adaptive-radius/hotspot":
            destination = ROOT/"output/adaptive-radius/demand-profile"
        demand_profile(destination)
    else:
        experiment(args)
