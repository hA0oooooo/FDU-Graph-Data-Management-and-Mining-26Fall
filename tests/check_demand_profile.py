from pathlib import Path
import hashlib,json,csv
from collections import Counter
p=Path("output/adaptive-radius/demand-profile")
def read(file):
    with file.open() as f:return list(csv.DictReader(f,delimiter="\t"))
def sha(file):
    with file.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
a=read(p/"construction.tsv")
b=read(p/"main.tsv")
c=read(p/"transfer.tsv")
assert len(a)==90 and len(b)==200 and len(c)==75
assert Counter(x["load"] for x in b)=={"mixed":175,"k4":25}
assert len({(x["graph"],x["method"],x["pair"]) for x in a})==90
assert len({(x["graph"],x["load"],x["method"],x["pair"]) for x in b})==200
assert len({(x["split"],x["method"],x["pair"]) for x in c})==75
assert all(x["candidate_equivalent"]=="True" for x in a)
assert sum(int(x["mismatches"]) for x in b+c)==0
all_receipts=list(p.rglob("receipt.json"))
assert len(all_receipts)==90+18+160+200+75
for path in all_receipts:
    rec=json.loads(path.read_text())
    for name,expected in rec["files"].items(): assert sha(path.parent/name)==expected,(path,name)
for graph in {x["graph"] for x in a}:
    group=[x for x in a if x["graph"]==graph]
    assert len({(x["config_sha256"],x["candidate_sha256"],x["table_sha256"],x["index_bytes"]) for x in group})==1
    details=[sha(p/"construction"/graph/m/"pair-1/query/details.tsv") for m in
             ("adaptive-full","adaptive-global","adaptive-demand")]
    assert len(set(details))==1
frozen=json.loads((p/"frozen.json").read_text())
assert len(frozen)==200
for x in b:
    base=f'{x["load"]}/{x["graph"]}/{x["method"]}/pair-{x["pair"]}'
    fit=frozen[base]
    assert x["config_sha256"]==fit["config_sha256"] and x["table_sha256"]==fit["table_sha256"]
    path=Path("dataset/workloads")/x["graph"]/"benchmark.tsv"
    qs=read(path)
    if x["load"]=="k4":qs=[r for r in qs if r["k"]=="4"]
    answers=read(p/"deploy"/base/"query/answers.tsv")
    assert len(qs)==len(answers)==int(x["queries"])
    assert all(int(y["yes"])==int(0<=int(q["d"])<=int(q["k"])) for q,y in zip(qs,answers))
for x in c:
    file=p/"workloads/email-EuAll"/(x["split"]+".tsv")
    assert sha(file)==x["query_sha256"]
    qs=read(file);answers=read(p/"transfer"/x["split"]/x["method"]/f'pair-{x["pair"]}'/"answers.tsv")
    assert len(qs)==len(answers)==int(x["queries"])
    assert all(int(y["yes"])==int(0<=int(q["d"])<=int(q["k"])) for q,y in zip(qs,answers))
meta=json.loads((p/"workloads/email-EuAll/manifest.json").read_text())
used=set(map(int,(p/"workloads/email-EuAll/excluded.txt").read_text().split()))
for split,record in meta["splits"].items():
    file=p/"workloads/email-EuAll"/(split+".tsv")
    assert sha(file)==record["sha256"]
    sources={int(x["s"]) for x in read(file)}
    assert not (used & sources)
    used.update(sources)
assert len(read(p/"historical.tsv"))==63
assert len(read(p/"summary.tsv"))==40
assert len(read(p/"transfer-combined.tsv"))==25
assert not list(p.rglob("*.pending"))
print("fixed construction records:",len(a),"main records:",len(b),"transfer records:",len(c))
print("verified process receipts:",len(all_receipts))
print("main decisions:",sum(int(x["queries"]) for x in b),"transfer decisions:",sum(int(x["queries"]) for x in c))
print("zero mismatches, all SHA-256 receipts verified")
