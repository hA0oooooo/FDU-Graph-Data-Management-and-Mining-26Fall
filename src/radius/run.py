"""Compile the CPU pilot and measure one frozen graph, from the repository root."""
import argparse
import csv
import hashlib
import json
import os
import socket
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from workload import QUERY_FILES, fixed_queries, workload_spec

HERE = Path(__file__).resolve().parent
BUILD = ROOT / "cache/radius"
WORKLOADS = ROOT / "dataset/workloads"


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def compile_tool(name):
    source = HERE / (name + ".cpp")
    binary = BUILD / name
    headers = list((ROOT / "src/radius").glob("*.hpp"))
    BUILD.mkdir(parents=True, exist_ok=True)
    if not binary.exists() or any(p.stat().st_mtime_ns > binary.stat().st_mtime_ns for p in [source, *headers]):
        with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
            fresh = Path(tmp) / name
            subprocess.run(["g++", "-O3", "-std=c++17", str(source), "-o", str(fresh)], check=True)
            fresh.replace(binary)
    return binary


def read_rows(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))


def prior_sources(work):
    path = work / "prior-sources.txt"
    return {int(s) for s in path.read_text().splitlines()} if path.exists() else set()


def prepare(n, edges, work):
    used = prior_sources(work)
    name = work.name
    work.mkdir(parents=True, exist_ok=True)
    binary = compile_tool("workloads")
    excl = BUILD / (name + "-excluded.txt")
    excl.write_text("".join(f"{v}\n" for v in sorted(used)))
    subprocess.run([binary, str(n), edges, excl, work], check=True)
    manifest = dict(nodes=n, graph_sha256=digest(edges), seed=25112026, splits={})
    for split in ["train", "validation", "test"]:
        path = work / (split + ".tsv")
        rows = read_rows(path)
        sources = {int(q["s"]) for q in rows}
        if sources & used:
            raise ValueError("shared sources")
        used.update(sources)
        classes = {"within": 0, "beyond": 0, "unreachable": 0}
        for q in rows:
            d, k = int(q["d"]), int(q["k"])
            classes["unreachable" if d < 0 else "beyond" if d > k else "within"] += 1
        manifest["splits"][split] = dict(sha256=digest(path), queries=len(rows), sources=len(sources), **classes)
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def export_comparison(dest, metadata):
    from statistics import median
    query=WORKLOADS/metadata["graph"]/metadata["query_name"]
    truth=[str(int(0<=int(q["d"])<=int(q["k"]))) for q in read_rows(query)
           if metadata["fixed_k"] is None or int(q["k"])==metadata["fixed_k"]]
    builds={r["method"]:r for r in read_rows(dest/"build.tsv")}
    repeated=read_rows(dest/"repeats.tsv")
    rounds={m:[r for r in repeated if r["method"]==m] for m in [*builds,"bibfs"]}
    reference=median(float(r["mean_us"]) for r in rounds["bibfs"])
    rows=[]
    for measured in read_rows(dest/"comparison.tsv"):
        name=measured["method"]
        b=builds[name]
        n=int(measured["queries"])
        answers=[r["answer"] for r in read_rows(dest/"methods"/name/"answers.tsv")]
        if n!=metadata["queries"] or int(measured["mismatches"]) or answers!=truth:
            raise ValueError("candidate comparison is incomplete or incorrect")
        batch_s=int(measured["batch_ns"])/1e9
        build_s=sum(float(b[key]) for key in ("root_ms","profile_ms","training_ms","choose_ms","build_ms"))/1000
        label_bytes=int(b["table_bytes"])
        method={"uniform":"uniform-h","structural":"adaptive-structural-h","workload":"adaptive-workload-h","uniform-active":"uniform-active-h"}[name]
        trial=rounds[name]
        latency=median(float(r["mean_us"]) for r in trial)
        scans=median(int(r["scans"]) for r in trial)
        certificates=median(int(r["upper"])+int(r["lower"]) for r in trial)
        row=dict(graph=metadata["graph"],method=method,status="verified",expected=n,checked=n,mismatches=0,
                 build_s=build_s,batch_s=batch_s,mean_us=batch_s*1e6/n,index_payload_bytes=label_bytes,
                 process_peak_kib=None,query_sha256=metadata["query_sha256"],graph_sha256=metadata["graph_sha256"],
                 receipt="comparison.tsv",answers=f"methods/{name}/answers.tsv",
                 execution_memory_gib=metadata["memory_gib"],comparison_budget_gib=metadata["memory_gib"],
                 solver_threads=1,host=metadata["host"],cpu_affinity=",".join(map(str,metadata["cpu_affinity"])),
                 cpu_count=metadata["cpu_count"],concurrent_configurations=1,
                 label_budget_multiple=metadata["label_budget_multiple"],retained_labels=int(b["labels"]),
                 median_query_us=latency,bibfs_median_query_us=reference,median_speedup=reference/latency,
                 median_scans=scans,certificate_fraction=certificates/n,shared_peak_kib=int((dest/"peak_kib.txt").read_text()))
        rows.append(row)
        target=dest/"methods"/name
        (target/"build.json").write_text(json.dumps(dict(b,build_s=build_s,metadata=metadata),indent=2)+"\n")
        (target/"query.json").write_text(json.dumps(row,indent=2)+"\n")
    with (dest/"performance.tsv").open("w") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter="\t",lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--nodes", required=True, type=int)
    ap.add_argument("--fixed-k", choices=[2,4,6], type=int, help="select, build and evaluate using just this threshold")
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--query-name", choices=QUERY_FILES, default="test.tsv")
    ap.add_argument("--active-uniform", action="store_true", help="compare workload-selected roots with a shared nonzero radius")
    ap.add_argument("--label-budget-multiple", type=int, default=4, help="retained-label budget as a multiple of |V|")
    ap.add_argument("--memory-gib", type=int, default=48)
    ap.add_argument("--cpu-count", type=int, default=1)
    ap.add_argument("--output", type=Path, help="measurement directory; defaults to output/adaptive-radius/<graph>")
    a = ap.parse_args()
    edges = ROOT / "dataset/prepared" / (a.graph + ".edges")
    work = WORKLOADS / a.graph
    if not (work / "manifest.json").exists() or a.prepare_only:
        prepare(a.nodes, edges, work)
    if a.prepare_only:
        return
    manifest = json.loads((work / "manifest.json").read_text())
    if manifest["nodes"] != a.nodes or manifest["graph_sha256"] != digest(edges):
        raise ValueError("graph differs from workload manifest")
    for name, spec in manifest["splits"].items():
        if digest(work / (name + ".tsv")) != spec["sha256"]:
            raise ValueError("query file changed: " + name)
    if a.query_name != "test.tsv":
        benchmark=work/a.query_name
        benchmark_manifest, spec=workload_spec(work,a.query_name)
        if benchmark_manifest["graph_sha256"] != manifest["graph_sha256"] or digest(benchmark) != spec["sha256"]:
            raise ValueError("benchmark input differs from freeze")
    dest = a.output or ROOT / "output/adaptive-radius" / a.graph
    if a.query_name != "test.tsv" and not a.output:
        dest = dest / Path(a.query_name).stem
    if a.fixed_k and not a.output:
        dest = dest / "fixed-k" / str(a.fixed_k)
    if a.label_budget_multiple!=4 and not a.output:
        dest = dest / f"budget-{a.label_budget_multiple}n"
    if a.active_uniform and not a.output:
        dest = dest / "active-uniform"
    dest.mkdir(parents=True, exist_ok=True)
    available=sorted(os.sched_getaffinity(0))
    if not 1<=a.cpu_count<=len(available) or a.memory_gib<1 or a.label_budget_multiple<1:
        ap.error("choose positive memory and an available CPU count")
    cpus=available[:a.cpu_count]
    os.sched_setaffinity(0,cpus)
    query=work/a.query_name
    query_hash=digest(query)
    if a.fixed_k is not None:
        selected,count=fixed_queries(query,a.fixed_k)
        query_hash=hashlib.sha256(selected.encode()).hexdigest()
    else:
        count=len(read_rows(query))
    metadata=dict(graph=a.graph, graph_sha256=manifest["graph_sha256"], query_sha256=query_hash,
                  query_name=a.query_name,fixed_k=a.fixed_k,queries=count,memory_gib=a.memory_gib,
                  label_budget_multiple=a.label_budget_multiple,active_uniform=a.active_uniform,
                  comparison_budget_gib=a.memory_gib,execution_memory_gib=a.memory_gib,
                  cpu_affinity=cpus,cpu_count=len(cpus),solver_threads=1,concurrent_configurations=1,
                  host=socket.gethostname())
    binary = compile_tool("measure")
    fingerprint=hashlib.sha256()
    for path in sorted([HERE/"measure.cpp",HERE/"index.hpp",HERE/"graph.hpp",HERE/"run.py"]):
        fingerprint.update(path.name.encode())
        fingerprint.update(path.read_bytes())
    metadata.update(source_sha256=fingerprint.hexdigest(),binary_sha256=digest(binary),
                    git_revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip())
    (dest/"run.json").write_text(json.dumps(metadata,indent=2)+"\n")
    memory=a.memory_gib*2**30
    subprocess.run(["prlimit",f"--as={memory}:{memory}","--","/usr/bin/time", "-f", "%M", "-o", str(dest / "peak_kib.txt"),
                    binary, str(a.nodes), edges, work, dest, str(a.fixed_k or -1), a.query_name, str(a.label_budget_multiple), str(int(a.active_uniform))], check=True)
    export_comparison(dest,metadata)
    print(a.graph, f"k={a.fixed_k}" if a.fixed_k else "mixed k",
          read_rows(dest / "repeats.tsv")[0]["n"], "test queries passed")


if __name__ == "__main__":
    main()
