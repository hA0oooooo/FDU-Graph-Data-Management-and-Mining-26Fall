"""Verify frozen graph bytes, benchmark identity, group membership and source separation."""
from collections import Counter
from functools import lru_cache
import csv
import hashlib
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


@lru_cache(maxsize=None)
def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def rows(path):
    with path.open() as stream:
        return [(int(q["s"]),int(q["t"]),int(q["k"]),int(q["d"]))
                for q in csv.DictReader(stream,delimiter="\t")]


def verify_files(root, name, specification, frozen):
    prepared = root/"prepared"
    files = [(prepared/f"{name}.edges", frozen["edges_sha256"]),
             (prepared/f"{name}.nodes.tsv", frozen["node_map_sha256"])]
    if "raw_sha256" in frozen:
        files.append((root/"raw"/specification["url"].rsplit("/",1)[-1], frozen["raw_sha256"]))
    for path, expected in files:
        assert sha(path)==expected, path
    return len(files)


def verify(work, frozen):
    original=load(work/"manifest.json")
    benchmark=load(work/"benchmark.json")
    n=original["nodes"]
    assert benchmark["nodes"]==n==frozen["nodes"],work
    assert benchmark["graph_sha256"]==original["graph_sha256"]==frozen["edges_sha256"],work
    assert benchmark["seed"]==26112026,work
    excluded=set()
    prior=work/"prior-sources.txt"
    if prior.exists(): excluded.update(map(int,prior.read_text().splitlines()))
    for path in work.rglob("*.tsv"):
        if not path.name.startswith("benchmark"):
            excluded.update(q[0] for q in rows(path))
    groups={}
    for group,metadata in benchmark["groups"].items():
        path=work/f"benchmark-{group}.tsv"
        data=rows(path)
        assert sha(path)==metadata["sha256"] and len(data)==metadata["queries"],path
        assert all(0<=s<n and 0<=t<n and k in (2,4,6) and -1<=d<n and
                   ((s==t)==(d==0)) for s,t,k,d in data),path
        assert len({q[:3] for q in data})==len(data),path
        sources={q[0] for q in data}
        assert len(sources)==64==metadata["sources"] and not sources&excluded,path
        excluded.update(sources)
        classes=Counter(f"{k}:"+("unreachable" if d<0 else "within" if d<=k else "beyond")
                        for _,_,k,d in data)
        assert dict(classes)==metadata["classes"],path
        if group=="uniform":
            assert set(Counter((s,k) for s,_,k,_ in data).values())=={64},path
        groups[group]=data
    assert set(groups)=={"uniform","stratified"},work
    merged=work/"benchmark.tsv"
    data=rows(merged)
    spec=benchmark["splits"]["benchmark"]
    assert sha(merged)==spec["sha256"] and len(data)==spec["queries"],merged
    assert Counter(data)==Counter(q for group in groups.values() for q in group),merged
    assert len({q[:3] for q in data})==len(data),merged
    return len(data)


if __name__=="__main__":
    root=Path(__file__).resolve().parents[1]/"dataset"
    specs=load(root/"manifest.json")|load(root/"catalogue.json")|load(root/"synthetic.json")
    total=0
    file_checks=0
    for name,spec in sorted(specs.items()):
        frozen=spec if "edges_sha256" in spec else load(root/"frozen"/f"{name}.json")
        file_checks+=verify_files(root,name,spec,frozen)
        count=verify(root/"workloads"/name,frozen)
        total+=count
        print(name,count)
    print(len(specs),"graphs,",total,"queries and",file_checks,"graph file hashes verified")
