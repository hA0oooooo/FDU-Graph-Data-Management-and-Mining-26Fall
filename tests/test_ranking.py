"""Check amortization, common-graph ranks and timing compatibility."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rank_results import aggregate, evaluate
from test_pareto import row


def sample(graph, method, seconds, build=0, allocated=0, status="verified"):
    return dict(row(method, 10, build, seconds, status), graph=graph,
                index_allocated_bytes=str(allocated), timing_protocol="warmup_median", query_repeats="5")


class RankingTest(unittest.TestCase):
    def test_amortization_and_coverage(self):
        data = [
            sample("a", "bibfs", 1e-4),
            sample("a", "esti", 2e-5, 4, 2**20),
            sample("b", "bibfs", 2e-4),
            sample("b", "esti", 0, status="allocation_failed"),
        ]
        results = evaluate(data, [10**6, 10**9], strict=True)
        a = {r["method"]: r for r in results if r["graph"] == "a"}
        self.assertAlmostEqual(a["esti"]["as_q1000000"], 10/6)
        self.assertAlmostEqual(a["esti"]["as_q1000000000"], 10/2.004)
        self.assertEqual(a["esti"]["break_even_queries"], 500000)
        self.assertEqual(a["esti"]["rank_as_q1000000"], 1)
        self.assertEqual(a["bibfs"]["rank_allocated_index"], 1)
        self.assertNotIn("cp_allocated_per_mib", a["bibfs"])
        self.assertAlmostEqual(a["esti"]["cp_allocated_per_mib"], 5)
        summary = {r["method"]: r for r in aggregate(results, [10**6, 10**9])}
        self.assertEqual(summary["esti"]["common_graph_names"], "a")
        self.assertEqual(summary["esti"]["verified_graphs"], 1)
        self.assertAlmostEqual(summary["esti"]["geomean_as_q1000000"], 10/6)

    def test_different_timing_and_incomplete_fixed(self):
        ref = sample("a", "bibfs", 1e-4)
        legacy = dict(sample("a", "esti", 1e-5), timing_protocol="first_batch", query_repeats="")
        incomplete = dict(sample("a", "kreach-2", 1e-5), expected="3", checked="3")
        with self.assertRaises(ValueError):
            evaluate([ref, legacy], [10**6], strict=True)
        results = {p["method"]: p for p in evaluate([ref, legacy, incomplete], [10**6])}
        self.assertEqual(results["esti"]["status"], "different_timing_protocol")
        self.assertEqual(results["kreach"]["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
