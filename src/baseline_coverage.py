"""Summarize every collected baseline configuration without mixing timing protocols."""
import argparse
import csv
from pathlib import Path


def read(path):
    with path.open() as stream:
        rows=list(csv.DictReader(stream,delimiter="\t"))
    result={(r["graph"],r["method"]):r for r in rows}
    if len(result)!=len(rows):
        raise ValueError(f"{path}: duplicate configuration")
    return result


def capacity_receipt(root, row):
    graph, method = row["graph"], row["method"]
    k=method.removeprefix("kreach-")
    for name in ("kreach-partition-capacity.tsv","kreach-capacity.tsv"):
        path=root/"historical"/name
        if not path.exists():
            continue
        with path.open() as stream:
            certificates=list(csv.DictReader(stream,delimiter="\t"))
        for r in certificates:
            if (r["graph"],r["k"],r["payload_lower_bytes"])==(graph,k,row["lower_bytes"]):
                if int(row["lower_bytes"])<=int(row["physical_memory_bytes"]):
                    raise ValueError(f"{graph} {method}: lower bound does not exceed physical capacity")
                return str(path.relative_to(root))
    raise ValueError(f"{graph} {method}: missing matching capacity certificate")


def combine(root):
    strict=read(root/"performance.tsv")
    historical=read(root/"historical/performance.tsv")
    pressure=read(root/"pressure/reviewed_performance.tsv")
    if not strict.keys()<=historical.keys() or not pressure.keys()<=historical.keys():
        raise ValueError("unexpected configuration outside historical graph/method inventory")
    if strict.keys() & pressure.keys():
        raise ValueError("strict and pressure configurations overlap")
    result=[]
    for key, prior in sorted(historical.items()):
        row=strict.get(key) or pressure.get(key) or prior
        source=("performance.tsv" if key in strict else
                "pressure/reviewed_performance.tsv" if key in pressure else "historical/performance.tsv")
        for field in ("graph_sha256","query_sha256"):
            if row.get(field) and row[field]!=prior[field]:
                raise ValueError(f"{key}: {field} differs")
        status=row["status"]
        if status=="verified" and (row.get("expected")!=row.get("checked") or row.get("mismatches")!="0"):
            raise ValueError(f"{key}: incorrect verification receipt")
        receipt=row.get("receipt")
        if receipt:
            folder=root/row["run"] if row.get("run") else (root/source).parent
            path=folder/receipt
            if not path.is_file():
                raise FileNotFoundError(path)
            receipt=str(path.relative_to(root))
        elif status=="physical_capacity_proved":
            receipt=capacity_receipt(root,row)
        result.append(dict(graph=key[0],method=key[1],status=status,source_table=source,
                           receipt=receipt or "",original_status=prior["status"],
                           expected=row.get("expected") or prior.get("expected"),
                           checked=row.get("checked") or "",
                           mismatches=row.get("mismatches") or "",
                           memory_gib=row.get("execution_memory_gib") or "",
                           timing_protocol=row.get("timing_protocol") or "",
                           lower_bytes=row.get("lower_bytes") or ""))
    return result


def write(root):
    rows=combine(root)
    target=root/"coverage.tsv"
    temp=target.with_suffix(".part")
    with temp.open("w") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter="\t",lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(target)
    return rows


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path,nargs="?",default=Path("output/baselines"))
    rows=write(parser.parse_args().root)
    from collections import Counter
    print(len(rows),dict(Counter(r["status"] for r in rows)))

