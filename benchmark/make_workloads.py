"""Generate diagnostic, source-disjoint workloads with exact distances."""
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path
import random


ROOT = Path(__file__).resolve().parents[1]
SEED = 20261125
CONFIRMATION_SEED = 20261126
KS = (2, 4, 6)
PER_CLASS = 30


def full_distances(adj, source):
    """Independent oracle: exhaust the outgoing component in the original graph."""
    distance = [-1] * len(adj)
    distance[source] = 0
    queue = deque([source])
    while queue:
        u = queue.popleft()
        for v in adj[u]:
            if distance[v] == -1:
                distance[v] = distance[u] + 1
                queue.append(v)
    return distance


def pick_sources(adj, pool):
    active = [s for s in pool if adj[s]][:64]
    sinks = [s for s in pool if not adj[s]][:12]
    return active + sinks


def source_splits(adj, graph):
    permutation = list(range(len(adj)))
    random.Random(f"{SEED}/{graph}/sources").shuffle(permutation)
    selected = set()
    for i, name in enumerate(("validation", "test")):
        sources = pick_sources(adj, permutation[i::2])
        selected.update(sources)
        yield name, sources, SEED
    # Exclude *candidates* even when none of their targets survived stratification.
    remaining = [s for s in range(len(adj)) if s not in selected]
    random.Random(f"{CONFIRMATION_SEED}/{graph}/sources").shuffle(remaining)
    yield "confirmation", pick_sources(adj, remaining), CONFIRMATION_SEED


def diverse_order(per_source, rng):
    """Interleave sources; each contributes once before any contributes twice."""
    queues = [rows for rows in per_source if rows]
    rng.shuffle(queues)
    return [rows[i] for i in range(PER_CLASS) for rows in queues if i < len(rows)]


def balanced_edges(boundary, rest):
    selected = boundary[:PER_CLASS // 2] + rest[:PER_CLASS // 2]
    extras = boundary[PER_CLASS // 2:] + rest[PER_CLASS // 2:]
    return selected + extras[:PER_CLASS - len(selected)]


def build_workload(adj, sources, rng):
    candidates = defaultdict(list)
    for source in sources:
        distance = full_distances(adj, source)
        by_dist = defaultdict(list)
        for target, d in enumerate(distance):
            if target != source:
                by_dist[d].append(target)
        for k in KS:
            groups = {
                "at_k": by_dist[k],
                "positive": [t for d, vs in by_dist.items() if 0 < d < k for t in vs],
                "at_k1": by_dist[k + 1],
                "too_far": [t for d, vs in by_dist.items() if d > k + 1 for t in vs],
                "unreachable": by_dist[-1],
            }
            for group, targets in groups.items():
                sample = rng.sample(targets, min(len(targets), PER_CLASS))
                candidates[k, group].append([(source, t, k, distance[t]) for t in sample])
    rows = []
    for k in KS:
        def ordered(group):
            return diverse_order(candidates[k, group], rng)
        rows.extend(balanced_edges(ordered("at_k"), ordered("positive")))
        rows.extend(balanced_edges(ordered("at_k1"), ordered("too_far")))
        rows.extend(ordered("unreachable")[:PER_CLASS])
    rng.shuffle(rows)
    return rows


def write_split(folder, split, rows):
    content = "s\tt\tk\td\n" + "".join(f"{s}\t{t}\t{k}\t{d}\n" for s, t, k, d in rows)
    raw = content.encode("ascii")
    target = folder / f"{split}.tsv"
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError(f"regenerated workload differs from frozen {target}")
    else:
        target.write_bytes(raw)
    summary = {}
    for k in KS:
        ds = [d for _, _, threshold, d in rows if threshold == k]
        counts = Counter(ds)
        summary[str(k)] = dict(positive=sum(0 <= d <= k for d in ds),
                               too_far=sum(d > k for d in ds), unreachable=counts[-1],
                               at_k=counts[k], at_k_plus_one=counts[k + 1])
    return dict(rows=len(rows), sources=len({s for s, *_ in rows}),
                sha256=hashlib.sha256(raw).hexdigest(), by_k=summary)


def main():
    catalogue = json.loads((ROOT / "dataset/manifest.json").read_text())
    all_stats = {}
    output = ROOT / "benchmark/workloads"
    for name, spec in sorted(catalogue.items()):
        raw = (ROOT / "dataset/prepared" / f"{name}.edges").read_bytes()
        if hashlib.sha256(raw).hexdigest() != spec["edges_sha256"]:
            raise ValueError(f"{name}: input differs from frozen graph")
        adj = [[] for _ in range(spec["nodes"])]
        for line in raw.splitlines():
            u, v = map(int, line.split())
            adj[u].append(v)
        folder = output / name
        folder.mkdir(parents=True, exist_ok=True)
        all_stats[name] = {}
        for split, sources, seed in source_splits(adj, name):
            rng = random.Random(f"{seed}/{name}/{split}")
            rows = build_workload(adj, sources, rng)
            assert len(rows) == len({(s, t, k) for s, t, k, _ in rows})
            all_stats[name][split] = write_split(folder, split, rows)
            print(f"{name} {split}: {len(rows)} queries", flush=True)
    summary = dict(seed=SEED, confirmation_seed=CONFIRMATION_SEED,
                   max_queries_per_k_class=PER_CLASS, graphs=all_stats)
    (output / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
