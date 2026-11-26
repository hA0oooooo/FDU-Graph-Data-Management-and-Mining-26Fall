"""Verify fair aggregation of fixed thresholds and the Pareto definition."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from plot_pareto import points


def row(method, size, build, batch, status="verified"):
    return dict(graph="g",method=method,graph_sha256="g-hash",query_sha256="q-hash",
                expected=str(size),checked=str(size) if status=="verified" else "",
                status=status,mismatches="0" if status=="verified" else "",build_s=str(build),batch_s=str(batch),index_payload_bytes="0",
                process_peak_kib="100",execution_memory_gib="48",comparison_budget_gib="48",
                solver_threads="1",build_threads="1",cpu_count="1",cpu_affinity="0",host="host",concurrent_configurations="1")


class ParetoTest(unittest.TestCase):
    def test_mixed_thresholds_and_dominance(self):
        data=points([row("bfs",3,0,3),row("bibfs",3,0,1.5),
                     row("kreach-2",1,1,.2),row("kreach-4",2,2,.3),
                     row("esti",3,2,2)],strict=True)
        result={p["method"]:p for p in data}
        self.assertEqual(result["kreach"]["build_s"],3)
        self.assertAlmostEqual(result["kreach"]["batch_s"],.5)
        self.assertEqual({p["method"] for p in data if p["pareto"]},{"bibfs","kreach"})

    def test_incomplete_and_different_resources(self):
        rows=[row("bibfs",3,0,3),row("kreach-2",1,1,.2),
              row("kreach-4",2,2,.3,"capacity_proved")]
        self.assertFalse(next(p for p in points(rows) if p["method"]=="kreach")["pareto"])
        rows[1]["cpu_affinity"]="1"
        with self.assertRaises(ValueError):
            points(rows,strict=True)


if __name__=="__main__":
    unittest.main()
