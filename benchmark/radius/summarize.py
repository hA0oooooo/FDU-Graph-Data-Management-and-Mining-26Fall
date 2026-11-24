"""Join measured costs and correctness by graph and exact query-file hash."""
import csv
import json
from math import ceil
from pathlib import Path
from statistics import median

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"results/round2"


def table(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))


def read(path):
    return json.loads(path.read_text())


def write(name, rows):
    with (OUT/name).open("w") as f:
        w=csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def radius(name, path):
    reps=table(path/"repeats.tsv")
    builds={r["method"]:r for r in table(path/"build.tsv")}
    by={m:[r for r in reps if r["method"]==m] for m in ("bibfs","uniform","structural","workload")}
    rows=[]
    for m,rs in by.items():
        assert len(rs)==12
        r=rs[0]; n=int(r["n"])
        b=builds.get(m,{})
        latency=[float(x["mean_us"]) for x in rs]
        prep=sum(float(b.get(k,0)) for k in ("root_ms","profile_ms","training_ms","choose_ms","build_ms"))
        def gaps(other):
            return [float(y["mean_us"])-v for y,v in zip(by[other],latency)]
        vs_uniform=gaps("uniform"); vs_bfs=gaps("bibfs")
        saved=median(vs_bfs)
        rows.append(dict(graph=name,method=m,n=n,mean_us=round(median(latency),4),
                         p95_us=round(median(float(x["p95_us"]) for x in rs),4),
                         edges=r["scans"],upper=r["upper"],lower=r["lower"],trivial=r["trivial"],
                         fallback=r["fallback"],entries=b.get("labels",0),table_bytes=b.get("table_bytes",0),
                         preprocess_ms=round(prep,4),wins_vs_uniform=sum(v>0 for v in vs_uniform),
                         paired_us_saved_vs_uniform=round(median(vs_uniform),4),
                         wins_vs_bibfs=sum(v>0 for v in vs_bfs),paired_us_saved_vs_bibfs=round(saved,4),
                         estimated_payback_queries_vs_bibfs=ceil(prep*1000/saved) if saved>0 else ""))
    return rows


def baselines(name,path):
    work=read(ROOT/"benchmark/radius/workloads"/name/"manifest.json")
    digest=work["splits"]["test"]["sha256"]
    expected_n=work["splits"]["test"]["queries"]
    rows=[]
    def record(method,status,n="",errors="",build="",queries="",detail=""):
        rows.append(dict(graph=name,method=method,status=status,checked=n if errors!="" else "",errors=errors,
                         build_ms=build,batch_query_ms=queries,config=detail,test_sha256=digest))
    hist=read(path/"historical.json")
    assert hist["test_sha256"]==digest and hist["graph_sha256"]==work["graph_sha256"]
    e=hist["esti"]
    record("ESTI",e["status"],e.get("queries",""),e.get("mismatches",""),e.get("build_ms",""),e.get("batch_ms",""),
           "upstream capacity" if "edge_slots" in e else "author commit d893a28")
    if "esti_expanded" in hist:
        x=hist["esti_expanded"]
        record("ESTI (capacity adjusted)",x["status"],x.get("queries",""),x.get("mismatches",""),
               x.get("build_ms",""),x.get("batch_ms",""),f"edge slots={x['edge_slots']}")
    for x in hist["kreach"]:
        ok=x["status"]=="passed"
        record("K-Reach 2012",x["status"],x.get("queries",""),x.get("mismatches",""),
               x["build_ns"]/1e6 if ok else "",x["median_batch_ns"]/1e6 if ok else "",f"k={x['k']}")
    if (path/"historical-extended.json").exists():
        extra=read(path/"historical-extended.json")
        assert extra["test_sha256"]==digest and extra["graph_sha256"]==work["graph_sha256"]
        for x in extra["kreach"]:
            ok=x["status"]=="passed"
            record("K-Reach 2012 extended",x["status"],x.get("queries",""),x.get("mismatches",""),
                   x["build_ns"]/1e6 if ok else "",x["median_batch_ns"]/1e6 if ok else "",f"k={x['k']}, 120s")
    scalable=read(ROOT/"baselines/scalable/radius"/(name+".json"))
    assert scalable["workload_sha256"]==digest and scalable["graph_sha256"]==work["graph_sha256"]
    for x in scalable["runs"]:
        record("Scalable 2014" if str(x["mode"]).isdigit() else "gen-k-reach",x["status"],x.get("n_queries",""),
               x.get("errors",""),x.get("build_s",0)*1000 if "build_s" in x else "",
               x.get("queries_s",0)*1000 if "queries_s" in x else "",
               f"mode={x['mode']}, b={scalable['b']}, D2={scalable['d2_cap']}")
    for mode in ("vcrea","vcrea-plus","pll"):
        report=read(ROOT/"baselines/cover/receipts/radius"/name/(mode+".json"))
        assert report["queries_sha256"]==digest and report["edges_sha256"]==work["graph_sha256"]
        x=report["results"][0]
        err=sum(v["mismatches"] for v in x["by_class"].values()) if "by_class" in x else ""
        record(mode,x["status"],x.get("queries",""),err,x["build_ns"]/1e6 if "build_ns" in x else "",
               x["query_ns"]/1e6 if "query_ns" in x else "",f"{report['wall_timeout_s']}s; {report['child_address_cap_bytes']//2**20}MiB")
    for x in rows:
        if x["status"] in ("ok","verified","passed"):
            assert x["errors"]==0
            if x["method"] not in ("K-Reach 2012","K-Reach 2012 extended","Scalable 2014"): assert x["checked"]==expected_n
    return rows


if __name__=="__main__":
    timing, history, matched, fixed=[],[],[],[]
    for path in sorted(x for x in OUT.iterdir() if x.is_dir()):
        audit_manifest=read(ROOT/"benchmark/radius/workloads"/path.name/"manifest.json")
        timing.extend(radius(path.name,path))
        pairs=table(path/"matched.tsv")
        a=[r for r in pairs if r["method"]=="workload"]
        b=[r for r in pairs if r["method"]=="structural-matched"]
        assert len(a)==len(b)==12 and int(b[0]["entries"])<=int(a[0]["entries"])
        gaps=[float(y["mean_us"])-float(x["mean_us"]) for x,y in zip(a,b)]
        matched.append(dict(graph=path.name, learned_entries=a[0]["entries"],structural_entries=b[0]["entries"],
                            learned_bytes=a[0]["bytes"], structural_bytes=b[0]["bytes"],learned_scans=a[0]["scans"],
                            structural_scans=b[0]["scans"],learned_hits=a[0]["hits"],structural_hits=b[0]["hits"],
                            paired_us_saved=round(median(gaps),4),workload_wins=sum(v>0 for v in gaps)))
        fixed_n=0
        for k in [2,4,6]:
            group=radius(path.name,path/"fixed-k"/str(k))
            fixed_n+=int(group[0]["n"])
            fixed.extend(dict(k=k,**row) for row in group)
        assert fixed_n==int(audit_manifest["splits"]["test"]["queries"])
        history.extend(baselines(path.name,path))
    write("radius-summary.tsv",timing)
    write("baseline-matrix.tsv",history)
    write("matched-summary.tsv",matched)
    write("fixed-summary.tsv",fixed)
