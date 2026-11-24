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
                         estimated_payback_queries_vs_bibfs=ceil(prep*1000/saved) if saved>0 else "NA"))
    return rows


def baselines(name,path):
    work=read(ROOT/"benchmark/radius/workloads"/name/"manifest.json")
    digest=work["splits"]["test"]["sha256"]
    expected_n=work["splits"]["test"]["queries"]
    rows=[]
    def record(method,status,n="",errors="",build="",queries="",detail=""):
        rows.append(dict(graph=name,method=method,status=status,checked=n if errors!="" else "",errors=errors,
                         build_ms=build,batch_query_ms=queries,config=detail,test_sha256=digest))
    prep={r["method"]:sum(float(r[k]) for k in ("root_ms","profile_ms","training_ms","choose_ms","build_ms"))
          for r in table(path/"build.tsv")}
    for served in table(path/"native-batch.tsv"):
        m=served["method"]
        record(m,"verified",int(served["n"]),0,round(prep.get(m,0),4),float(served["batch_ms"]),"native, one full batch")
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
               x["build_ns"]/1e6 if ok else "",x["first_batch_ns"]/1e6 if ok else "",f"k={x['k']}")
    if (path/"historical-extended.json").exists():
        extra=read(path/"historical-extended.json")
        assert extra["test_sha256"]==digest and extra["graph_sha256"]==work["graph_sha256"]
        for x in extra["kreach"]:
            ok=x["status"]=="passed"
            record("K-Reach 2012 extended",x["status"],x.get("queries",""),x.get("mismatches",""),
                   x["build_ns"]/1e6 if ok else "",x["first_batch_ns"]/1e6 if ok else "",f"k={x['k']}, 120s" + (", bad_alloc" if "bad_alloc" in x.get("detail","") else ""))
    scalable=read(ROOT/"baselines/scalable/radius"/(name+".json"))
    assert scalable["workload_sha256"]==digest and scalable["graph_sha256"]==work["graph_sha256"]
    for x in scalable["runs"]:
        record("Scalable 2014" if str(x["mode"]).isdigit() else "gen-k-reach",x["status"],x.get("n_queries",""),
               x.get("errors",""),x.get("build_s",0)*1000 if "build_s" in x else "",
               x.get("queries_s",0)*1000 if "queries_s" in x else "",
               f"mode={x['mode']}, b={scalable['b']}, D2={scalable['d2_cap']}")
    cover=ROOT/"baselines/cover/receipts"
    reports=[(mode, cover/"radius"/name/(mode+".json")) for mode in ("vcrea","vcrea-plus","pll")]
    for mode in ("vcrea","vcrea-plus","pll"):
        standard = cover/"standard"/name/(mode+".json")
        if standard.exists():
            reports.append((mode+" standard",standard))
    if (cover/"extended"/(name+".json")).exists():
        reports.append(("vcrea extended", cover/"extended"/(name+".json")))
    for mode, receipt in reports:
        report=read(receipt)
        assert report["queries_sha256"]==digest and report["edges_sha256"]==work["graph_sha256"]
        x=report["results"][0]
        err=sum(v["mismatches"] for v in x["by_class"].values()) if "by_class" in x else ""
        record(mode,x["status"],x.get("queries",""),err,x["build_ns"]/1e6 if "build_ns" in x else "",
               x["query_ns"]/1e6 if "query_ns" in x else "",f"{report['wall_timeout_s']}s; {report['child_address_cap_bytes']//2**20}MiB")
    for family in ("K-Reach 2012", "Scalable 2014"):
        pieces=[x for x in rows if x["method"]==family]
        assert len(pieces)==3
        if all(x["errors"]==0 for x in pieces):
            assert sum(x["checked"] for x in pieces)==expected_n
    for x in rows:
        if x["status"] in ("ok","verified","passed"):
            assert x["errors"]==0
            if x["method"] not in ("K-Reach 2012","K-Reach 2012 extended","Scalable 2014"): assert x["checked"]==expected_n
    return rows


def coverage(rows):
    """Show the smallest measured budget that returned and checked every answer."""
    by_graph = {}
    for row in rows:
        by_graph.setdefault(row["graph"], {}).setdefault(row["method"], []).append(row)
    complete = {"ok", "passed", "verified"}
    def status(r):
        if r["status"] in complete:
            return "ok"
        if "bad_alloc" in r["config"]:
            return "memory_limit"
        return r["status"]
    results = []
    for graph, methods in by_graph.items():
        row = {"graph": graph, "test_n": methods["bibfs"][0]["checked"]}
        for mode in ("bfs", "bibfs", "uniform", "workload"):
            row[mode] = status(methods[mode][0])
        for k in (2, 4, 6):
            trials = [r for m in ("K-Reach 2012", "K-Reach 2012 extended")
                      for r in methods.get(m, []) if r["config"].split(",")[0] == f"k={k}"]
            best = next((r for r in trials if status(r) == "ok"), trials[-1])
            row[f"K-Reach 2012 k={k}"] = status(best) + (" (120s)" if "extended" in best["method"] else " (20s)")
        row["Scalable 2014"] = f'{sum(status(r) == "ok" for r in methods["Scalable 2014"])}/3'
        row["gen-k-reach"] = status(methods["gen-k-reach"][0])
        row["ESTI"] = status(methods["ESTI"][0])
        if "ESTI (capacity adjusted)" in methods:
            row["ESTI"] += " / maxm adjusted " + status(methods["ESTI (capacity adjusted)"][0])
        for mode in ("vcrea", "vcrea-plus", "pll"):
            trials = [r for name in (mode, mode + " standard", mode + " extended")
                      for r in methods.get(name, [])]
            best = next((r for r in trials if status(r) == "ok"), trials[-1])
            row[mode] = f'{status(best)} ({best["config"]})'
        results.append(row)
    return results


if __name__=="__main__":
    timing, history, matched, fixed, heldouts, filters=[],[],[],[],[],[]
    for path in sorted(x for x in OUT.iterdir() if x.is_dir()):
        audit_manifest=read(ROOT/"benchmark/radius/workloads"/path.name/"manifest.json")
        timing.extend(radius(path.name,path))
        for mode in ("scc-two-orders","cover-tree"):
            rep=[row for row in table(path/"filters.tsv") if row["filter"]==mode]
            assert len(rep)==5 and all(int(row["queries"])==audit_manifest["splits"]["test"]["queries"] for row in rep)
            first=rep[0]
            filters.append(dict(graph=path.name,method=mode,queries=first["queries"],hits=first["hits"],
                                fallback_scans=first["scans"],build_ms=first["build_ms"],
                                mean_us=median(float(row["mean_us"]) for row in rep)))

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
        new=table(path/"holdouts-balanced.tsv")
        configs={r["method"]:r["radii"] for r in table(path/"build.tsv")}
        equal_configs=configs["uniform"]==configs["workload"]
        hmanifest=read(ROOT/"benchmark/radius/workloads"/path.name/"holdouts/manifest.json")
        for split in ["holdout-1","holdout-2","holdout-3"]:
            groups={m:[r for r in new if r["split"]==split and r["method"]==m]
                    for m in ["uniform","structural","workload","bibfs"]}
            n=hmanifest["splits"][split]["n"]
            assert all(len(rs)==12 and all(int(r["n"])==n for r in rs) for rs in groups.values())
            def diff(alt):
                return [float(b["mean_us"])-float(a["mean_us"]) for a,b in zip(groups["workload"],groups[alt])]
            gains=diff("uniform")
            rel=[100*g/float(r["mean_us"]) for g,r in zip(gains,groups["uniform"])]
            heldouts.append(dict(graph=path.name,split=split,identical_radii=equal_configs,n=n,sources=hmanifest["splits"][split]["sources"],
                                 workload_mean_us=median(float(r["mean_us"]) for r in groups["workload"]),
                                 uniform_mean_us=median(float(r["mean_us"]) for r in groups["uniform"]),
                                 paired_us_saved_vs_uniform=round(median(gains),4),
                                 paired_percent_saved_vs_uniform=round(median(rel),2),wins_vs_uniform=sum(x>0 for x in gains),
                                 paired_us_saved_vs_bibfs=round(median(diff("bibfs")),4),
                                 workload_scans=groups["workload"][0]["scans"],uniform_scans=groups["uniform"][0]["scans"]))
        history.extend(baselines(path.name,path))
    write("radius-summary.tsv",timing)
    write("baseline-matrix.tsv",history)
    write("baseline-coverage.tsv",coverage(history))
    write("filter-summary.tsv",filters)
    write("matched-summary.tsv",matched)
    write("fixed-summary.tsv",fixed)
    write("holdout-summary.tsv",heldouts)
