"""Run the historical baselines on the frozen common queries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from baselines.esti.build import ensure_built as build_esti
from radius.run import ROOT, WORKLOADS, compile_tool, digest, read_rows
from workload import QUERY_FILES, fixed_queries, workload_spec


def read_json(path):
    return json.loads(path.read_text())


def launch(script, *args, log, check=True):
    return subprocess.run([sys.executable, ROOT / "src" / script, *map(str, args)],
                          cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=check)


def input_for(graph, spec, query_name):
    work = WORKLOADS / graph
    queries = work / query_name
    edges = ROOT / "dataset/prepared" / f"{graph}.edges"
    manifest, test = workload_spec(work, query_name)
    if spec["nodes"] != manifest["nodes"] or digest(edges) != manifest["graph_sha256"] or digest(queries) != test["sha256"]:
        raise ValueError(f"{graph}: graph or query differs from frozen input")
    return work, edges, queries


def fixed_input(output, graph, spec, query_name, k):
    _, edges, original=input_for(graph,spec,query_name)
    folder=output/"inputs"
    folder.mkdir(exist_ok=True)
    queries=folder/(graph+".tsv")
    content,count=fixed_queries(original,k)
    if queries.exists() and queries.read_text()!=content:
        raise ValueError("fixed workload changed")
    queries.write_text(content)
    meta=dict(nodes=spec["nodes"],graph_sha256=digest(edges),source_sha256=digest(original),
              fixed_k=k,splits={graph:dict(sha256=digest(queries),queries=count)})
    queries.with_suffix(".json").write_text(json.dumps(meta,indent=2)+"\n")
    return queries


FAMILIES = ("search", "esti", "scalable", "vcrea", "vcrea-plus", "pll", "kreach")


def run_family(graph, spec, family, output, search, args):
    target = output / "methods" / family / graph
    target.mkdir(parents=True,exist_ok=True)
    _, edges, queries = input_for(graph, spec, args.query_name)
    if args.fixed_k is not None:
        queries=output/"inputs"/(graph+".tsv")
    query_arg=str(queries) if args.fixed_k is not None else args.query_name
    thresholds=1 if args.fixed_k is not None else 3
    answers=target/"answers"
    nodes = spec["nodes"]
    with (target / f"{family}.log").open("a") as log:
        if family == "search":
            result = target / "search.tsv"
            if result.exists() and len(read_rows(result)) == 2:
                return
            memory=args.memory_gib*2**30
            pieces=[]
            for method in ("bfs","bibfs"):
                piece=target/(method+".tsv")
                with piece.open("w") as data:
                    subprocess.run(["prlimit",f"--as={memory}:{memory}","--","/usr/bin/time","-f","%M",
                                    "-o",target/(method+".peak-kib.txt"),search,str(nodes),edges,queries,answers,method],
                                   stdout=data,stderr=log,check=True)
                pieces.append(piece.read_text().splitlines())
            result.write_text("\n".join(pieces[0]+pieces[1][1:])+"\n")
        elif family == "scalable":
            result = target / "scalable.json"
            if result.exists() and len(read_json(result)["runs"]) == thresholds+1:
                return
            launch("baselines/scalable/run.py", "--graph", edges, "--nodes", nodes, "--queries", queries,
                   "--b", args.b, "--d2-cap", args.d2_cap, "--memory-gib", args.memory_gib,
                   "--output", result, "--answers-dir", answers, log=log, check=False)
        elif family in ("vcrea","vcrea-plus","pll"):
            launch("baselines/cover/matrix.py", graph, "--methods", family, "--memory-mib", args.memory_gib*1024,
                   "--query-name", query_arg, "--output", output/"methods"/family, log=log)
        else:
            result = target / f"{family}.json"
            if result.exists():
                prior = read_json(result)
                if (family == "esti" and ("esti_expanded" in prior or prior.get("esti",{}).get("status")=="passed")
                    or family == "kreach" and len(prior["kreach"])==thresholds):
                    return
            launch("baselines/historical.py", "--graph", graph, "--nodes", nodes, "--edges", spec["edges"],
                   "--memory-gib", args.kreach_memory_gib if family=="kreach" else args.memory_gib,
                   "--query-name", query_arg, "--methods", family,
                   "--output", result, "--answers-dir", answers, "--resume", log=log)
    print(f"{graph}: {family} complete", flush=True)


def write_coverage(output, selected, query_name="test.tsv"):
    from report_baselines import records, write_table, write_method_results
    config=read_json(output/"run.json")
    if config.get("query_name","test.tsv")!=query_name or set(config["graphs"])!=set(selected):
        raise ValueError("review configuration differs from run")
    rows=[r for graph in selected for r in records(output,graph,config)]
    write_table(output/"coverage.tsv",[
        {k:r[k] for k in ("graph","method","status","expected","checked","mismatches")} for r in rows])
    write_table(output/"performance.tsv",rows)
    write_method_results(output,rows)
    print(f"{len(rows)} baseline configurations recorded in {output/'coverage.tsv'}")
    valid={"verified","timeout","time_limit","allocation_failed","capacity_proved","exceeds_upstream_capacity"}
    if any(r["status"] not in valid for r in rows):
        raise SystemExit("Incomplete or failed configurations remain in coverage.tsv")


def main():
    synthetic = read_json(ROOT / "dataset/synthetic.json")
    graphs = read_json(ROOT / "dataset/manifest.json") | read_json(ROOT / "dataset/catalogue.json") | synthetic
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graphs", nargs="*", metavar="GRAPH",
                        help="graph names or all")
    parser.add_argument("--review", type=Path, help="check and rebuild coverage.tsv from an existing run")
    parser.add_argument("--output", type=Path, help="named run directory; defaults to output/baselines/runs/<graph>-<workload>[-kN]")
    parser.add_argument("--query-name", choices=QUERY_FILES, default="benchmark.tsv")
    parser.add_argument("--b", type=int, default=1000)
    parser.add_argument("--d2-cap", type=int, default=128)
    parser.add_argument("--query-repeats", type=int, default=5)
    parser.add_argument("--memory-gib", type=int, default=48)
    parser.add_argument("--kreach-memory-gib", type=int, help="optional separate diagnostic limit")
    parser.add_argument("--cpu-count", type=int, help="logical CPUs; default 1 for serial, up to 72 for parallel runs")
    parser.add_argument("--fixed-k", type=int, choices=(2,4,6), help="all methods query one threshold")
    parser.add_argument("--resume", action="store_true", help="resume the same run directory")
    parser.add_argument("--jobs", type=int, default=1, help="parallel configurations; each solver is single-threaded")
    args = parser.parse_args()
    if args.review:
        if args.graphs or args.output:
            parser.error("--review expects only an existing run directory")
        recorded = read_json(args.review / "run.json")
        write_coverage(args.review, recorded["graphs"], recorded.get("query_name","test.tsv"))
        return
    if not args.graphs or set(args.graphs) - (graphs.keys() | {"all"}):
        parser.error("choose all or one of " + ", ".join(sorted(graphs)))
    if args.jobs < 1 or args.query_repeats<1:
        parser.error("--jobs and --query-repeats must be positive")
    if args.memory_gib<1 or (args.kreach_memory_gib is not None and args.kreach_memory_gib<1):
        parser.error("memory limits must be positive")
    args.kreach_memory_gib=args.kreach_memory_gib or args.memory_gib
    available=sorted(os.sched_getaffinity(0))
    args.cpu_count=args.cpu_count if args.cpu_count is not None else 1 if args.jobs==1 else min(72,len(available))
    if not 1<=args.cpu_count<=len(available) or args.jobs>args.cpu_count:
        parser.error("choose an available CPU count at least as large as --jobs")
    cpus=available[:args.cpu_count]
    os.sched_setaffinity(0,cpus)
    os.environ["KHOP_QUERY_REPEATS"]=str(args.query_repeats)
    selected = (sorted(graphs, key=lambda name: (graphs[name]["edges"], name))
                if "all" in args.graphs else list(dict.fromkeys(args.graphs)))
    group = "all" if "all" in args.graphs else selected[0] if len(selected)==1 else "selected"
    run_name = f"{group}-{Path(args.query_name).stem}"
    if args.fixed_k is not None:
        run_name += f"-k{args.fixed_k}"
    output = (args.output or ROOT / "output/baselines/runs" / run_name).resolve()
    output.mkdir(parents=True, exist_ok=args.resume)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    import hashlib
    source_hash = hashlib.sha256()
    for path in sorted((ROOT / "src").rglob("*")):
        if path.is_file() and path.suffix in (".py",".cpp",".hpp"):
            source_hash.update(str(path.relative_to(ROOT)).encode())
            source_hash.update(path.read_bytes())
    compiler = subprocess.check_output(["g++", "-dumpfullversion"], text=True).strip()
    metadata = dict(graphs=selected, host=socket.gethostname(),
                    jobs=args.jobs, git_revision=revision, source_sha256=source_hash.hexdigest(), compiler=compiler,
                    query_name=args.query_name, b=args.b, d2_cap=args.d2_cap,
                    memory_gib=args.memory_gib, kreach_memory_gib=args.kreach_memory_gib, timeout=None,
                    comparison_budget_gib=args.memory_gib, layout="method",
                    cpu_affinity=cpus, solver_threads=1, fixed_k=args.fixed_k,query_repeats=args.query_repeats)
    run_file = output / "run.json"
    if args.resume:
        prior = read_json(run_file)
        if any(prior.get(key)!=value for key,value in metadata.items() if key not in ("jobs","git_revision")):
            raise ValueError("resume requires the same run configuration")
    else:
        run_file.write_text(json.dumps(metadata, indent=2)+"\n")
    for graph in selected:
        edges = ROOT / "dataset/prepared" / f"{graph}.edges"
        if not edges.exists():
            script = ("generate_synthetic.py" if graph in synthetic else
                      "prepare.py" if graph in ("wiki-Vote","p2p-Gnutella31") else "freeze.py")
            subprocess.run([sys.executable, ROOT/"src"/script,graph], check=True)
        if args.query_name!="test.tsv" and not (WORKLOADS/graph/args.query_name).exists():
            subprocess.run([sys.executable, ROOT/"src/prepare_benchmark.py",graph],check=True)
        if args.fixed_k is not None:
            fixed_input(output,graph,graphs[graph],args.query_name,args.fixed_k)
    build_esti()
    search = compile_tool("search")
    # Finish online and partial-index families before expensive full-cover builds.
    import fcntl
    with (output / "run.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=args.jobs) as jobs:
            futures = [jobs.submit(run_family, name, graphs[name], family, output, search, args)
                       for family in FAMILIES for name in selected]
            for future in futures:
                future.result()
    write_coverage(output, selected, args.query_name)


if __name__ == "__main__":
    main()
