"""Evaluate the original ESTI kernel and fixed-k K-Reach on the frozen common workload."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import tempfile
from time import monotonic

from esti.build import BUILD as ESTI_CACHE, build
from esti.build_capacity import expanded

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "cache/historical"
FIELDS = ("k roots entries build_bfs_edge_scans build_ns process_peak_kib queries positives "
          "mismatches first_batch_ns median_batch_ns both_core source_core target_core neither_core index_bytes").split()


def cap(memory_gib):
    resource.setrlimit(resource.RLIMIT_AS, (memory_gib << 30, memory_gib << 30))
    resource.setrlimit(resource.RLIMIT_STACK, (256 << 20, 256 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_limited(command, work, seconds, memory_gib, progress=None):
    start = monotonic()
    if seconds is not None:
        command = ["timeout", "-k", "2", str(seconds), *command]
    if progress is None:
        p = subprocess.run(command, cwd=work, capture_output=True, text=True,
                           preexec_fn=lambda: cap(memory_gib))
    else:
        with progress.open("w") as log:
            p = subprocess.run(command, cwd=work, stdout=subprocess.PIPE, stderr=log, text=True,
                               preexec_fn=lambda: cap(memory_gib))
    record = dict(limit_seconds=seconds, memory_gib=memory_gib, wall_s=monotonic()-start, code=p.returncode)
    if p.returncode:
        record["status"] = "time_limit" if seconds is not None and p.returncode in (124, 137) else "failed"
        record["detail"] = ((progress.read_text() if progress else p.stderr) or p.stdout).strip()[-400:]
    else:
        record["status"] = "passed"
    return p, record


def compiled(source, name):
    dest = BUILD / name
    if not dest.exists() or dest.stat().st_mtime_ns < source.stat().st_mtime_ns:
        with tempfile.TemporaryDirectory(dir=BUILD) as folder:
            binary = Path(folder) / name
            subprocess.run(["g++", "-O3", "-std=c++17", source, "-o", binary], check=True)
            binary.replace(dest)
    return dest


def esti(n, m, edges, rows, work, adapted=False, memory_gib=48):
    if n >= 30000000 or (not adapted and m+n > 60000000):
        return dict(status="exceeds_upstream_capacity", vertex_slots=30000000, edge_slots=60000000)
    writer = compiled(ROOT / "src/baselines/esti/convert.cpp", "esti_format")
    binary = ESTI_CACHE / "esti"
    if not binary.exists():
        build()
    if adapted:
        # The author adds up to n edges from a virtual root after reading m input edges.
        binary = expanded(m+n+1)
    with (work / "graph").open("w") as f:
        subprocess.run([writer, str(n), str(m), edges], stdout=f, check=True)
    (work / "queries").write_text("".join(f"{s} {t} -2 {k}\n" for s, t, k, d in rows))
    p, rec = run_limited([binary, "graph", "queries", "cyc"], work, None, memory_gib)
    if adapted:
        rec.update(edge_slots=m+n+1, modification="maxm only")
    if p.returncode:
        return rec
    answers = (work / "answers.txt").read_text().splitlines()
    if len(answers)!=len(rows) or set(answers)-{"0","1"}:
        raise RuntimeError("incomplete ESTI answer stream")
    rec.update(queries=len(rows), mismatches=sum((x=="1") != (0<=d<=k)
               for x, (_, _, k, d) in zip(answers, rows)),
               build_ms=float(re.search(r"construction time: ([\d.]+) ms", p.stdout)[1]),
               batch_ms=float(re.search(r"query time: ([\d.]+) ms", p.stdout)[1]))
    if rec["mismatches"]:
        rec["status"] = "mismatch"
    return rec


def kreach(binary, n, edges, queries, rows, k, work, seconds, memory_gib, progress):
    p,record=run_limited([binary,str(n),edges,queries,str(k)],work,seconds,memory_gib,progress)
    record["k"]=k
    if p.returncode==0:
        record.update(zip(FIELDS,map(int,p.stdout.split()),strict=True))
        if record["mismatches"] or record["queries"]!=sum(row[2]==k for row in rows):
            record["status"]="mismatch"
    return record


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--nodes", type=int, required=True)
    ap.add_argument("--edges", type=int, required=True)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--kreach-seconds", type=int, help="optional wall-clock limit per fixed k")
    ap.add_argument("--memory-gib", type=int, default=96)
    ap.add_argument("--methods", nargs="+", choices=("esti","kreach"), default=["esti","kreach"])
    ap.add_argument("--k", nargs="+", type=int, help="specific fixed thresholds to build")
    ap.add_argument("--query-name", default="test.tsv")
    ap.add_argument("--resume", action="store_true")
    a=ap.parse_args()
    BUILD.mkdir(parents=True,exist_ok=True)
    edges=ROOT/"dataset/prepared"/(a.graph+".edges")
    queries=ROOT/"dataset/workloads"/a.graph/a.query_name
    with queries.open() as f:
        rows=[tuple(int(q[key]) for key in ("s","t","k","d")) for q in csv.DictReader(f,delimiter="\t")]
    manifest=json.loads((queries.parent/"manifest.json" if a.query_name=="test.tsv" else queries.with_suffix(".json")).read_text())
    if hashlib.sha256(queries.read_bytes()).hexdigest()!=manifest["splits"][queries.stem]["sha256"]:
        raise ValueError("workload hash mismatch")
    with edges.open("rb") as f:
        if hashlib.file_digest(f,"sha256").hexdigest()!=manifest["graph_sha256"]:
            raise ValueError("edge hash mismatch")
    receipt=dict(graph=a.graph, graph_sha256=manifest["graph_sha256"],
                 test_sha256=manifest["splits"][queries.stem]["sha256"], kreach=[])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    if a.resume and a.output.exists():
        prior=json.loads(a.output.read_text())
        if any(prior.get(k)!=v for k,v in receipt.items() if k!="kreach"):
            raise ValueError("resume input changed")
        receipt=prior
    def save():
        tmp=a.output.with_suffix(".json.part")
        tmp.write_text(json.dumps(receipt, indent=2)+"\n")
        tmp.replace(a.output)
    with tempfile.TemporaryDirectory(dir=BUILD) as folder:
        work=Path(folder)
        binary = compiled(ROOT / "src/baselines/kreach/kreach.cpp", "kreach")
        if "esti" in a.methods and "esti" not in receipt:
            receipt["esti"] = esti(a.nodes, a.edges, edges, rows, work, memory_gib=a.memory_gib)
            if receipt["esti"]["status"] == "exceeds_upstream_capacity" and a.nodes < 30000000:
                receipt["esti_expanded"] = esti(a.nodes, a.edges, edges, rows, work, adapted=True, memory_gib=a.memory_gib)
            save()
        if "kreach" in a.methods:
            for k in (a.k or sorted({row[2] for row in rows})):
                if any(row["k"]==k for row in receipt["kreach"]):
                    continue
                receipt["kreach"].append(kreach(binary, a.nodes, edges, queries, rows, k, work, a.kreach_seconds, a.memory_gib, a.output.with_suffix(f".k{k}.log").resolve()))
                save()



if __name__=="__main__":
    main()
