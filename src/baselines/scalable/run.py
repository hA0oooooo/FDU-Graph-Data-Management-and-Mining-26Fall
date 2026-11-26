"""Run Cheng et al. 2014 fixed and general K-Reach against exact distances on Linux."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def limit_memory(memory_gib):
    resource.setrlimit(resource.RLIMIT_AS, (memory_gib << 30, memory_gib << 30))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True, help="dense directed edge list")
    parser.add_argument("--nodes", type=int, required=True, help="include isolated vertices")
    parser.add_argument("--queries", type=Path, required=True, help="TSV with s, t, k, d")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--b", type=int, default=1000)
    parser.add_argument("--d2-cap", type=int, default=32)
    parser.add_argument("--timeout", type=int, help="optional wall seconds per configuration")
    parser.add_argument("--memory-gib", type=int, default=48)
    args = parser.parse_args()
    with args.queries.open() as f:
        queries = [(int(r["k"]), int(r["d"])) for r in csv.DictReader(f, delimiter="\t")]
    if not queries:
        raise ValueError("empty workload")
    compiler = subprocess.check_output(["g++","-dumpfullversion"],text=True).strip()
    result = dict(graph=args.graph.name, graph_sha256=sha(args.graph), nodes=args.nodes,
                  workload=args.queries.name, workload_sha256=sha(args.queries),
                  source_sha256=sha(HERE/"scalable.cpp"), compiler=compiler,
                  b=args.b, d2_cap=args.d2_cap, timeout_each_s=args.timeout,
                  address_space_gib=args.memory_gib, runs=[])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for source in ("selfcheck","scalable"):
            subprocess.run(["g++","-std=c++17","-O3",HERE/f"{source}.cpp","-o",tmp/source],check=True)
        result["selfcheck"] = json.loads(subprocess.check_output([tmp/"selfcheck"],text=True))
        for mode in [str(k) for k in sorted({k for k, _ in queries})]+["general"]:
            expected = [(k,d) for k,d in queries if mode=="general" or k==int(mode)]
            cmd = ["/usr/bin/time","-f","%M","-o",tmp/"rss",tmp/"scalable",
                   str(args.nodes),args.graph,args.queries,mode,str(args.b),
                   str(args.d2_cap),tmp/"predictions"]
            if args.timeout is not None:
                cmd = ["timeout","--kill-after=2",str(args.timeout),*cmd]
            try:
                run = subprocess.run(cmd,capture_output=True,text=True,
                                     preexec_fn=lambda: limit_memory(args.memory_gib),check=True)
                row = json.loads(run.stdout)
                outputs = (tmp/"predictions").read_text().splitlines()
                if len(outputs)!=len(expected) or set(outputs)-{"0","1"}:
                    raise ValueError("incomplete output")
                mistakes={group:0 for group in ("within_k","beyond_k","unreachable")}
                counts=mistakes.copy()
                for (k,d), answer in zip(expected,outputs):
                    group = "unreachable" if d<0 else "beyond_k" if d>k else "within_k"
                    counts[group]+=1
                    mistakes[group]+=(answer=="1") != (0<=d<=k)
                errors=sum(mistakes.values())
                row.update(mode=mode, status="mismatch" if errors else "verified",
                           errors=errors, by_class=counts, errors_by_class=mistakes,
                           peak_rss_kib=int((tmp/"rss").read_text()))
            except subprocess.CalledProcessError as e:
                row=dict(mode=mode,status="timeout" if args.timeout is not None and e.returncode==124 else "allocation_failed" if "bad_alloc" in e.stderr else "failed",
                         queries_requested=len(expected))
                row.update(returncode=e.returncode, stderr=e.stderr[-240:])
            result["runs"].append(row)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2)+"\n")
            print(mode,row["status"],row.get("build_s"),row.get("n_queries"),flush=True)
    if any(row["status"]!="verified" for row in result["runs"]):
        raise SystemExit(1)


if __name__=="__main__":
    main()
