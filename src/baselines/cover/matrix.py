"""Measure all three competitive variants on any ready frozen workloads."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from run import HERE, ROOT, METHODS, hash_file, measure, save, write_requests
sys.path.insert(0,str(ROOT/"src"))
from workload import workload_spec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("graphs", nargs="*", help="defaults to all frozen workloads")
    ap.add_argument("--output", type=Path, required=True, help="directory of per-method receipts")
    ap.add_argument("--timeout", type=int, help="uniform per-method limit in seconds")
    ap.add_argument("--methods", nargs="+", choices=METHODS[:3], default=METHODS[:3])
    ap.add_argument("--query-name", default="test.tsv", help="file in each frozen workload directory")
    ap.add_argument("--memory-mib", type=int, default=49152)
    args = ap.parse_args()
    if args.timeout is not None and args.timeout <= 0 or args.memory_mib <= 0:
        ap.error("resource limits must be positive")
    workloads = ROOT / "dataset/workloads"
    graphs = args.graphs or sorted(p.parent.name for p in workloads.glob("*/manifest.json"))
    src = HERE / "labels.cpp"
    src_sha = hash_file(src)
    flags = ["-O3", "-std=c++17"]
    cap = args.memory_mib * 1024**2
    compiler = subprocess.check_output(["g++","-dumpfullversion"],text=True).strip()
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        binary = work/"labels"
        for graph in graphs:
            timeout = args.timeout
            edges = ROOT/"dataset/prepared"/f"{graph}.edges"
            queries = workloads/graph/args.query_name
            meta, query_spec = workload_spec(queries.parent,args.query_name)
            n = meta["nodes"]
            inputs = dict(graph=graph,nodes=n,source_sha256=src_sha,flags=flags,
                          compiler=compiler,child_address_cap_bytes=cap,wall_timeout_s=timeout,
                          degree_threshold=1,edges_sha256=meta["graph_sha256"],
                          queries_file=queries.name,queries_sha256=query_spec["sha256"])
            jobs = []
            for method in args.methods:
                path = args.output/graph/f"{method}.json"
                if path.exists():
                    prior = json.loads(path.read_text())
                    if any(prior.get(key) != value for key,value in inputs.items()):
                        raise ValueError(f"previous receipt differs from these inputs: {path}")
                    continue
                jobs.append((method,path))
            if not jobs:
                continue
            if hash_file(edges) != inputs["edges_sha256"] or hash_file(queries) != inputs["queries_sha256"]:
                raise ValueError(f"{graph}: graph or query differs from workload manifest")
            if not binary.exists():
                subprocess.run(["g++",*flags,src,"-o",binary],check=True)
            with queries.open() as f:
                rows = [tuple(map(int,(r["s"],r["t"],r["k"],r["d"]))) for r in csv.DictReader(f,delimiter="\t")]
            if not rows or len(rows) != query_spec["queries"]:
                raise ValueError(f"{graph}: invalid workload size")
            qp = work / "requests"
            write_requests(qp,rows)
            for method,path in jobs:
                path.parent.mkdir(parents=True, exist_ok=True)
                result = measure(binary,graph,method,n,edges,qp,rows,timeout,cap,path.with_suffix(".log"),path.with_suffix(".answers.tsv"))
                save(path,dict(inputs,results=[result]))
                print(graph,method,result["status"],round(result["elapsed_s"],2),flush=True)
                if result["status"] == "mismatch":
                    raise ValueError(f"correctness failure: {path}")


if __name__ == "__main__":
    main()
