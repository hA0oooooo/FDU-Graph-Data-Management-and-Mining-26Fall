"""Inspect baseline runs using a common table of exactness and resource metrics."""
import argparse
import csv
import json
from pathlib import Path
from collections import Counter
from baselines.cover.capacity_report import verify as verify_label_capacity
from radius.run import ROOT, WORKLOADS, digest, read_rows


def load(path):
    return json.loads(path.read_text())


def read_config(run, graph):
    query = WORKLOADS / graph / run.get("query_name", "test.tsv")
    manifest = load(query.parent/"manifest.json" if query.name=="test.tsv" else query.with_suffix(".json"))
    frozen = manifest["splits"][query.stem]
    if digest(query)!=frozen["sha256"]:
        raise ValueError(f"{graph}: query hash mismatch")
    counts = Counter(int(q["k"]) for q in read_rows(query))
    return manifest["graph_sha256"], frozen["sha256"], frozen["queries"], counts


def capacity_status(run_dir, graph, receipt, row):
    """A cancelled build is capacity-proved only with a matching strict lower bound."""
    if "bad_alloc" in row.get("detail", ""):
        return "allocation_failed"
    path = run_dir / "capacity_decisions.json"
    if row.get("code") != -15 or not path.exists():
        return row["status"]
    decisions = [d for d in load(path) if d["graph"] == graph and d["k"] == row["k"]]
    if not decisions:
        return row["status"]
    if len(decisions) != 1:
        raise ValueError("duplicate capacity evidence")
    decision = decisions[0]
    proof = decision["proof"]
    if (decision["graph_sha256"] != receipt["graph_sha256"] or
        decision["test_sha256"] != receipt["test_sha256"] or
        decision["memory_gib"] != row["memory_gib"] or
        proof["graph"] != graph or int(proof["k"]) != row["k"] or
        int(proof["payload_lower_bytes"]) <= row["memory_gib"] * 2**30):
        raise ValueError(f"{graph}: invalid K-Reach capacity certificate")
    return "capacity_proved"


def label_capacity_status(run_dir, graph, method, receipt, row):
    path=run_dir/"label_capacity_decisions.json"
    if row.get("returncode")!=-15 or not path.exists():
        return row["status"]
    decisions=[d for d in load(path) if (d["graph"],d["method"])==(graph,method)]
    if not decisions:
        return row["status"]
    if len(decisions)!=1:
        raise ValueError("duplicate label capacity evidence")
    d=decisions[0]
    proof=d["proof"]
    if (d["graph_sha256"]!=receipt["edges_sha256"] or d["query_sha256"]!=receipt["queries_sha256"] or
        d["source_sha256"]!=receipt["source_sha256"] or
        d["memory_gib"]*2**30!=receipt["child_address_cap_bytes"] or
        (proof["graph"],proof["method"],proof["memory_gib"])!=(graph,method,d["memory_gib"])):
        raise ValueError(f"{graph}: label capacity certificate input mismatch")
    verify_label_capacity(proof)
    return "capacity_proved"


def records(run_dir, graph, config):
    edge_hash, query_hash, expected, counts = read_config(config,graph)
    dest = run_dir / graph
    result = {}
    def item(name, row, status, checked=None, errors=None, build=None, query=None, size=None, rss=None):
        n=counts[int(name.rsplit("-",1)[1])] if name.startswith(("scalable-","kreach-")) else expected
        valid=status in ("passed","verified","ok")
        result[name] = dict(graph=graph, method=name,
             status=("verified" if checked==n and errors==0 else "invalid") if valid else status,
             expected=n, checked=checked if valid else None, mismatches=errors if valid else None,
             build_s=build if valid else None, batch_s=query if valid else None,
             mean_us=query*1e6/n if valid and query is not None else None,
             index_payload_bytes=size if valid else None, process_peak_kib=rss if valid else None,
             query_sha256=query_hash, graph_sha256=edge_hash)

    if (dest/"search.tsv").exists():
        for r in read_rows(dest/"search.tsv"):
            item(r["method"],r,"verified",int(r["queries"]),int(r["mismatches"]),0,
                 float(r["batch_ms"])/1000,0)
    historical = dest/"historical.json"
    files = [historical] if historical.exists() else [dest/"esti.json",dest/"kreach.json"]
    profile=run_dir/"esti-profile"/(graph+".json")
    if profile.exists():
        files.append(profile)
    for file in files:
        if not file.exists():
            continue
        r = load(file)
        if (r["graph_sha256"],r["test_sha256"])!=(edge_hash,query_hash):
            raise ValueError(f"{file}: input mismatch")
        for method in ("esti","esti_expanded"):
            if method in r:
                row=r[method]
                item(method,row,row["status"],row.get("queries"),row.get("mismatches"),
                     row.get("build_ms",0)/1000,row.get("batch_ms",0)/1000,
                     row.get("index_bytes"),row.get("process_peak_kib"))
        for row in r.get("kreach",[]):
            status=capacity_status(run_dir, graph, r, row)
            item(f"kreach-{row['k']}",row,status,row.get("queries"),row.get("mismatches"),
                 row.get("build_ns",0)/1e9,row.get("first_batch_ns",0)/1e9,
                 row.get("index_bytes"),row.get("process_peak_kib"))
    file=dest/"scalable.json"
    if file.exists():
        r=load(file)
        if (r["graph_sha256"],r["workload_sha256"])!=(edge_hash,query_hash):
            raise ValueError(f"{file}: input mismatch")
        for row in r["runs"]:
            method="gen-k-reach" if row["mode"]=="general" else f"scalable-{row['mode']}"
            size=None
            if "D1" in row and "D2" in row:
                size=sum(8*row[d]["endpoint_labels"]+4*row[d]["dense_core_slots"] for d in ("D1","D2"))
            item(method,row,row["status"],row.get("n_queries"),row.get("errors"),row.get("build_s"),
                 row.get("queries_s"),size,row.get("peak_rss_kib"))
    for method in ("vcrea","vcrea-plus","pll"):
        file=run_dir/"labels"/graph/(method+".json")
        parallel=run_dir/"parallel-labels"/graph/(method+".json")
        if parallel.exists():
            file=parallel
        if not file.exists():
            continue
        r=load(file)
        if (r["edges_sha256"],r["queries_sha256"])!=(edge_hash,query_hash):
            raise ValueError(f"{file}: input mismatch")
        if (r.get("child_address_cap_bytes") not in (None, config.get("memory_gib",0)*2**30)
                and config.get("query_name")=="benchmark.tsv"):
            raise ValueError(f"{file}: memory cap differs")
        row=r["results"][0]
        if row["method"]!=method:
            raise ValueError(f"{file}: method mismatch")
        classes=row.get("by_class")
        checked=sum(c["n"] for c in classes.values()) if classes else None
        errors=sum(c["mismatches"] for c in classes.values()) if classes else None
        item(method,row,label_capacity_status(run_dir,graph,method,r,row),checked,errors,row.get("build_ns",0)/1e9,
             row.get("query_ns",0)/1e9,row.get("encoded_bytes"),row.get("process_peak_kib"))

    methods = ["bfs","bibfs","esti","gen-k-reach","vcrea","vcrea-plus","pll"]
    methods += [f"{name}-{k}" for name in ("scalable","kreach") for k in sorted(counts)]
    if ("esti_expanded" in result or (result.get("esti") and
                     result["esti"]["status"]=="exceeds_upstream_capacity")):
        methods.append("esti_expanded")
    for method in methods:
        if method not in result:
            item(method,{}, "pending")
    return [result[m] for m in methods]


def write_table(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".part")
    with tmp.open("w") as file:
        writer=csv.DictWriter(file,fieldnames=rows[0],delimiter="\t",lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs",type=Path,nargs="+")
    parser.add_argument("--output",type=Path,help="merged performance.tsv path for multiple disjoint runs")
    args=parser.parse_args()
    if len(args.runs)>1 and not args.output:
        parser.error("multiple runs require --output")
    rows=[]
    graphs=set()
    protocol=None
    for run in args.runs:
        config=load(run/"run.json")
        common=tuple(config.get(k) for k in
            ("host","compiler","query_name","b","d2_cap","memory_gib","kreach_memory_gib","timeout"))
        if protocol is None:
            protocol=common
        elif common!=protocol:
            raise ValueError("merged runs use different configurations")
        if graphs & set(config["graphs"]):
            raise ValueError("merged runs contain overlapping graphs")
        graphs.update(config["graphs"])
        records_for_run=[r for graph in config["graphs"] for r in records(run,graph,config)]
        write_table(run/"performance.tsv",records_for_run)
        rows.extend(dict(r,run=run.name,git_revision=config.get("git_revision",""),
                         b=config.get("b",""),d2_cap=config.get("d2_cap","")) for r in records_for_run)
        print(run,dict(Counter(r["status"] for r in records_for_run)),flush=True)
    if args.output:
        write_table(args.output,rows)
    counts=Counter(r["status"] for r in rows)
    if counts["invalid"] or counts["mismatch"]:
        raise SystemExit("a correctness check failed")


if __name__=="__main__":
    main()
