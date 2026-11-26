"""Check the fixed author implementation against all-pairs Floyd on small graphs."""
from pathlib import Path
import random
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/"src"/"baselines"))
from historical import BUILD, esti
from esti.build import BINARY as ESTI_BINARY, build


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    if not ESTI_BINARY.exists():
        build()
    rng = random.Random(26112026)
    cases = [(3, [(s,t) for s in range(3) for t in range(3) if mask & (1 << (s*3+t))])
             for mask in range(512)]
    cases += [(9, [(s,t) for s in range(9) for t in range(9) if rng.random() < prob])
              for prob in (0.1,0.35,0.75) for _ in range(8)]
    comparisons = 0
    with tempfile.TemporaryDirectory(dir=BUILD) as tmp:
        folder = Path(tmp)
        for i,(n, edges) in enumerate(cases):
            d = [[n+1]*n for _ in range(n)]
            for v in range(n):
                d[v][v] = 0
            for s,t in edges:
                d[s][t] = min(d[s][t],1)
            for v in range(n):
                for s in range(n):
                    for t in range(n):
                        d[s][t] = min(d[s][t],d[s][v]+d[v][t])
            rows = [(s,t,k,d[s][t] if d[s][t]<n else -1)
                    for s in range(n) for t in range(n) for k in range(n+1)]
            graph = folder/"fixture.edges"
            graph.write_text("".join(f"{s}\t{t}\n" for s,t in edges))
            result = esti(n,len(edges),graph,rows,folder)
            if result["status"] != "passed" or result.get("mismatches"):
                raise AssertionError((i,edges,result))
            comparisons += len(rows)
    print(f"{len(cases)} ESTI graphs, {comparisons} exact comparisons passed")


if __name__=="__main__":
    main()
