"""Run the frozen two-graph pilot from the repository root, using only stdlib."""
import argparse
import csv
import gc
import json
import math
import os
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter, perf_counter_ns
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from khop import IndexBudgetError, bfs, bibfs, build_index, choose_landmarks


def read_graph(name):
    pairs = []
    with (ROOT / "dataset" / "prepared" / f"{name}.edges").open() as f:
        for line in f:
            u, v = line.split()
            pairs.append((int(u), int(v)))
    n = max(max(edge) for edge in pairs) + 1
    out = [[] for _ in range(n)]
    inc = [[] for _ in range(n)]
    for u, v in pairs:
        out[u].append(v)
        inc[v].append(u)
    return out, inc


def read_split(name, split):
    path = ROOT / "benchmark" / "workloads" / name / f"{split}.tsv"
    with path.open() as f:
        return [tuple(int(row[key]) for key in ("s", "t", "k", "d"))
                for row in csv.DictReader(f, delimiter="\t")]


def timed_pass(query, rows):
    times, events = [], []
    for s, t, k, d in rows:
        start = perf_counter_ns()
        answer, route, scans = query(s, t, k)
        times.append(perf_counter_ns() - start)
        if answer != (0 <= d <= k):
            raise AssertionError(f"incorrect result at {(s, t, k, d)}: {answer}")
        events.append((route, scans))
    return times, events


def search_query(search, out, inc):
    def run(s, t, k):
        answer, scans = search(out, inc, s, t, k)
        return answer, "search", scans
    return run


def p95(times):
    return sorted(times)[math.ceil(len(times) * 0.95) - 1]


def measured_build(out, inc, roots, mode, h, cap):
    start = perf_counter()
    idx = build_index(out, inc, roots, mode, h, cap)
    elapsed = perf_counter() - start
    return idx, {"radius_limit": h, "build_s": elapsed, "entries": idx.entries,
                 "build_scans": idx.build_scans, "radii_in_out": idx.radii}


def memory_probe(out, inc, roots, mode, h, cap):
    # A separate, untimed build isolates Python allocations with the graph resident.
    gc.collect()
    tracemalloc.start()
    try:
        index = build_index(out, inc, roots, mode, h, cap)
        current, peak = tracemalloc.get_traced_memory()
        return {"traced_index_bytes": current, "traced_build_peak_bytes": peak}
    finally:
        tracemalloc.stop()


def tune(out, inc, roots, cap, valid, validation):
    scores = []
    for h in range(7):
        start = perf_counter()
        try:
            idx, metrics = measured_build(out, inc, roots, "uniform", h, cap)
        except IndexBudgetError as err:
            validation.append(dict(h=h, feasible=False, build_s=perf_counter()-start,
                                   build_scans=err.build_scans, reason=str(err)))
            continue
        query_us = []
        for _ in range(3):
            times, _ = timed_pass(idx.query, valid)
            query_us.append(sum(times) / len(valid) / 1000)
        score = median(query_us)
        validation.append(dict(h=h, feasible=True, entries=idx.entries,
                               build_s=metrics["build_s"], build_scans=idx.build_scans, val_mean_us=score,
                               repetitions_us=query_us))
        scores.append((score, h))
        del idx
    return min(scores)[1]


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, rows[0].keys(), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def distance_class(d, k):
    if d < 0:
        return "unreachable"
    return "within_k" if d <= k else "beyond_k"


def benchmark(name, dest):
    dest.mkdir(parents=True, exist_ok=True)
    valid = read_split(name, "validation")
    test = read_split(name, "test")
    if {s for s, *_ in valid} & {s for s, *_ in test}:
        raise ValueError("validation and test sources overlap")
    out, inc = read_graph(name)
    cap = 4 * len(out)
    start = perf_counter()
    roots = list(choose_landmarks(out, inc, 12))
    select_s = perf_counter() - start
    validation = []
    start = perf_counter()
    chosen = tune(out, inc, roots, cap, valid, validation)
    tuning_s = perf_counter() - start
    queries = {"bfs": search_query(bfs, out, inc), "bibfs": search_query(bibfs, out, inc)}
    builds = {}
    for mode, h in [("uniform", chosen), ("adaptive", 6)]:
        idx, builds[mode] = measured_build(out, inc, roots, mode, h, cap)
        queries[mode] = idx.query
    # Allocate no timing instrumentation inside the search or the index.
    summaries, by_class, test_runs = [], [], []
    methods = list(queries)
    last_events = {}
    for repeat in range(5):
        order = methods[repeat % len(methods):] + methods[:repeat % len(methods)]
        for method in order:
            times, events = timed_pass(queries[method], test)
            if repeat and events != last_events[method]:
                raise ValueError(f"non-deterministic routes: {method}")
            last_events[method] = events
            test_runs.append(dict(repeat=repeat+1, method=method, n=len(test),
                                  mean_us=sum(times)/len(test)/1000,
                                  p95_us=p95(times)/1000))
    for method, events in last_events.items():
        repeats = [r for r in test_runs if r["method"] == method]
        summaries.append(dict(method=method, n=len(test), errors=0,
                              mean_us=median(r["mean_us"] for r in repeats),
                              p95_us=median(r["p95_us"] for r in repeats),
                              scans=sum(e for _, e in events),
                              upper=sum(o == "upper" for o, _ in events),
                              lower=sum(o == "lower" for o, _ in events),
                              trivial=sum(o == "trivial" for o, _ in events),
                              fallback=sum(o == "fallback" for o, _ in events)))
        groups = {}
        for (_, _, k, d), (route, scans) in zip(test, events):
            key = (k, distance_class(d, k))
            row = groups.setdefault(key, dict(method=method, k=k, distance_class=key[1],
                                               n=0, edges=0, search=0, upper=0,
                                               lower=0, trivial=0, fallback=0))
            row["n"] += 1
            row["edges"] += scans
            row[route] += 1
        by_class.extend(groups[key] for key in sorted(groups))
    for mode, h in [("uniform", chosen), ("adaptive", 6)]:
        builds[mode].update(memory_probe(out, inc, roots, mode, h, cap))
    write_csv(dest / "summary.csv", summaries)
    write_csv(dest / "repeats.csv", test_runs)
    write_csv(dest / "by_class.csv", by_class)
    metadata = dict(graph=name, nodes=len(out), edges=sum(map(len, out)),
                    python=platform.python_version(), cpu_affinity=sorted(os.sched_getaffinity(0)),
                    entry_cap=cap, landmarks=roots, landmark_selection_s=select_s,
                    uniform_validation=validation, uniform_tuning_s=tuning_s,
                    chosen_uniform_h=chosen, builds=builds)
    (dest / "build.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", choices=["wiki-Vote", "p2p-Gnutella31"], required=True)
    parser.add_argument("--output", type=Path, required=True, help="results directory for this graph")
    args = parser.parse_args()
    benchmark(args.graph, args.output)
