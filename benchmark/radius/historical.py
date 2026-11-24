"""Evaluate the original ESTI kernel and fixed-k K-Reach on round-two inputs."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
from time import monotonic

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build/radius"
FIELDS = ("k roots entries build_bfs_edge_scans build_ns process_peak_kib queries positives "
          "mismatches first_batch_ns median_batch_ns both_core source_core target_core neither_core").split()


def cap():
    resource.setrlimit(resource.RLIMIT_AS, (6 << 30, 6 << 30))
    resource.setrlimit(resource.RLIMIT_STACK, (256 << 20, 256 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_limited(command, work, seconds):
    start = monotonic()
    p = subprocess.run(["timeout", "-k", "2", str(seconds), *command], cwd=work,
                       capture_output=True, text=True, preexec_fn=cap)
    record = dict(limit_seconds=seconds, wall_s=monotonic()-start, code=p.returncode)
    if p.returncode:
        record["status"] = "time_limit" if p.returncode in (124, 137) else "failed"
        record["detail"] = (p.stderr or p.stdout).strip()[-400:]
    else:
        record["status"] = "passed"
    return p, record


def compiled(source, name):
    dest = BUILD / name
    if not dest.exists() or dest.stat().st_mtime_ns < source.stat().st_mtime_ns:
        subprocess.run(["g++", "-O3", "-std=c++17", source, "-o", dest], check=True)
    return dest


def esti(n, m, edges, rows, work, adapted=False):
    if n >= 30000000 or (not adapted and m+n > 60000000):
        return dict(status="exceeds_upstream_capacity", vertex_slots=30000000, edge_slots=60000000)
    writer = compiled(ROOT / "baselines/esti/convert.cpp", "esti_format")
    binary = ROOT / "baselines/esti/_build/esti"
    if not binary.exists():
        subprocess.run(["python3", str(ROOT / "baselines/esti/build.py")], check=True)
    if adapted:
        # The author adds up to n edges from a virtual root after reading m input edges.
        sys.path.insert(0, str(ROOT / "baselines/esti"))
        from build_capacity import expanded
        binary = expanded(m+n+1)
    with (work / "graph").open("w") as f:
        subprocess.run([writer, str(n), str(m), edges], stdout=f, check=True)
    (work / "queries").write_text("".join(f"{s} {t} -2 {k}\n" for s, t, k, d in rows))
    p, rec = run_limited([binary, "graph", "queries", "cyc"], work, 100)
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


def kreach(binary, n, edges, queries, rows, k, work, seconds):
    p,record=run_limited([binary,str(n),edges,queries,str(k)],work,seconds)
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
    ap.add_argument("--extend-from", type=Path, help="retry only 20s K-Reach timeouts from this primary receipt at 120s")
    a=ap.parse_args()
    BUILD.mkdir(parents=True,exist_ok=True)
    edges=ROOT/"dataset/prepared"/(a.graph+".edges")
    queries=ROOT/"benchmark/radius/workloads"/a.graph/"test.tsv"
    with queries.open() as f:
        rows=[tuple(int(q[key]) for key in ("s","t","k","d")) for q in csv.DictReader(f,delimiter="\t")]
    manifest=json.loads((queries.parent/"manifest.json").read_text())
    if hashlib.sha256(queries.read_bytes()).hexdigest()!=manifest["splits"]["test"]["sha256"]:
        raise ValueError("workload hash mismatch")
    with edges.open("rb") as f:
        if hashlib.file_digest(f,"sha256").hexdigest()!=manifest["graph_sha256"]:
            raise ValueError("edge hash mismatch")
    receipt=dict(graph=a.graph, graph_sha256=manifest["graph_sha256"],
                 test_sha256=manifest["splits"]["test"]["sha256"], kreach=[])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=BUILD) as folder:
        work=Path(folder)
        binary=compiled(ROOT/"baselines/kreach/kreach.cpp","kreach")
        ks=(2,4,6)
        seconds=20
        if a.extend_from:
            primary=json.loads(a.extend_from.read_text())
            if primary["test_sha256"]!=receipt["test_sha256"] or primary["graph_sha256"]!=receipt["graph_sha256"]:
                raise ValueError("primary receipt input mismatch")
            ks=[x["k"] for x in primary["kreach"] if x["status"]=="time_limit"]
            seconds=120
        else:
            receipt["esti"]=esti(a.nodes,a.edges,edges,rows,work)
            if receipt["esti"]["status"]=="exceeds_upstream_capacity" and a.nodes<30000000:
                receipt["esti_expanded"]=esti(a.nodes,a.edges,edges,rows,work,adapted=True)
        a.output.write_text(json.dumps(receipt,indent=2)+"\n")
        for k in ks:
            receipt["kreach"].append(kreach(binary,a.nodes,edges,queries,rows,k,work,seconds))
            a.output.write_text(json.dumps(receipt,indent=2)+"\n")


if __name__=="__main__":
    main()
