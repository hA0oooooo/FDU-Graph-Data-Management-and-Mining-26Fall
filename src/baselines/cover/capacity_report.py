"""Aggregate disjoint canonical-label witnesses and an already-built prefix."""
import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def rows(path):
    # A live counter flushes one complete row per root batch.
    for line in path.read_text().splitlines(keepends=True):
        if line.endswith("\n"):
            graph, family, roots, first, end, h, basic, plus, _ = line.split("\t")
            yield dict(graph=graph, family=family, roots=int(roots), first=int(first),
                       end=int(end), h=int(h), basic=int(basic), plus=int(plus))


def bounds(folder, memory_gib):
    original = load(folder/"jobs.json")
    packed = {(x["graph"], x["method"]):x for x in load(folder/"jobs-packed.json")}
    results = []
    for job in original:
        graph, family = job["graph"], job["method"]
        first = job["first"]
        end = first
        samples = []
        for batch in rows(Path(job["counts_path"])):
            if batch["first"] != end:
                raise ValueError(f"{graph}: noncontiguous scalar samples")
            samples.append(batch)
            end = batch["end"]
        continuation = packed[graph, family]
        if continuation["first"] != end:
            raise ValueError(f"{graph}: packed range overlaps scalar samples")
        for batch in rows(Path(continuation["counts_path"])):
            if batch["first"] != end:
                raise ValueError(f"{graph}: noncontiguous packed samples")
            samples.append(batch)
            end = batch["end"]
        if any(b["graph"]!=graph or b["family"]!=family or b["end"]<=b["first"] or
               b["basic"]<0 or b["plus"]<b["basic"] for b in samples):
            raise ValueError("invalid witness counts")
        sources=[Path(job["counts_path"]), Path(continuation["counts_path"])]
        for method in ("vcrea", "vcrea-plus") if family=="cover" else ("pll",):
            key="plus" if method=="vcrea-plus" else "basic"
            entries=job["previous_entries"] + sum(b[key] for b in samples)
            results.append(dict(graph=graph, method=method, prefix_roots=first,
                   prefix_entries=job["previous_entries"], prefix_log=job["previous_prefix"],
                   through_root=end, batches=samples, lower_entries=entries, lower_bytes=2*entries,
                   sources=[str(path) for path in sources], memory_gib=memory_gib,
                   exceeds_capacity=2*entries>memory_gib*2**30))
    return results


def verify(evidence):
    """Recheck the numeric and root-range components of a saved certificate."""
    first=evidence["prefix_roots"]
    end=first
    method=evidence["method"]
    family="pll" if method=="pll" else "cover"
    key="plus" if method=="vcrea-plus" else "basic"
    entries=evidence["prefix_entries"]
    prefix=evidence["prefix_log"]
    if first:
        if not prefix or not prefix.startswith(f"roots={first}/") or f"labels={entries} " not in prefix:
            raise ValueError("invalid observed prefix")
    elif entries or prefix:
        raise ValueError("unexpected nonempty prefix")
    for b in evidence["batches"]:
        if (b["graph"],b["family"],b["first"])!=(evidence["graph"],family,end):
            raise ValueError("overlapping or mismatched witness")
        if not end<b["end"]<=b["roots"] or not 0<=b["basic"]<=b["plus"]:
            raise ValueError("invalid witness range")
        end=b["end"]
        entries+=b[key]
    if (end!=evidence["through_root"] or entries!=evidence["lower_entries"] or
            2*entries!=evidence["lower_bytes"] or 2*entries<=evidence["memory_gib"]*2**30):
        raise ValueError("certificate does not establish a strict capacity lower bound")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder",type=Path)
    parser.add_argument("--memory-gib",type=int,default=48)
    args=parser.parse_args()
    result=bounds(args.folder,args.memory_gib)
    target=args.folder/"bounds.json"
    tmp=target.with_suffix(".part")
    tmp.write_text(json.dumps(result,indent=2)+"\n")
    tmp.replace(target)
    print("graph\tmethod\tthrough_root\tlower_gib\texceeds_capacity")
    for item in result:
        print(f"{item['graph']}\t{item['method']}\t{item['through_root']}\t"
              f"{item['lower_bytes']/2**30:.3f}\t{item['exceeds_capacity']}")


if __name__=="__main__":
    main()
