import itertools
import random
import unittest

from src.khop import IndexBudgetError, bfs, bibfs, build_index, choose_landmarks


def graph(n, edges):
    out = [[] for _ in range(n)]
    inc = [[] for _ in range(n)]
    for u, v in edges:
        out[u].append(v)
        inc[v].append(u)
    return out, inc


def distances(out):
    # Independent all-pairs oracle for small graphs, including isolated vertices.
    n = len(out)
    d = [[float("inf")] * n for _ in out]
    for u, row in enumerate(out):
        for v in row:
            d[u][v] = 1
        d[u][u] = 0
    for p, u, v in itertools.product(range(n), repeat=3):
        d[u][v] = min(d[u][v], d[u][p] + d[p][v])
    return d


class TestKHop(unittest.TestCase):
    def check_graph(self, out, inc):
        oracle = distances(out)
        roots = choose_landmarks(out, inc, 2)
        indices = [
            build_index(out, inc, roots, "uniform", 0, 4),
            build_index(out, inc, roots, "uniform", 2, len(out) * 4),
            build_index(out, inc, roots, "adaptive", 3, 6),
        ]
        for s, t in itertools.product(range(len(out)), repeat=2):
            for k in range(5):
                expected = oracle[s][t] <= k
                for method in (bfs, bibfs):
                    self.assertEqual(method(out, inc, s, t, k)[0], expected)
                for idx in indices:
                    result, how, scans = idx.query(s, t, k)
                    self.assertEqual(result, expected)
                    self.assertIn(how, ("upper", "lower", "fallback", "trivial"))
                    if how != "fallback":
                        self.assertEqual(scans, 0)

    def test_all_three_vertex_graphs(self):
        edges = list(itertools.product(range(3), repeat=2))
        for mask in range(1 << len(edges)):
            selected = [e for i, e in enumerate(edges) if mask & (1 << i)]
            self.check_graph(*graph(3, selected))

    def test_random_graphs(self):
        rng = random.Random(17)
        for _ in range(25):
            selected = [e for e in itertools.product(range(8), repeat=2) if rng.random() < 0.2]
            self.check_graph(*graph(8, selected))

    def test_partial_layer_rolls_back_and_charges_scans(self):
        out, inc = graph(4, [(0, 1), (0, 2), (0, 3), (1, 0)])
        self.assertEqual(choose_landmarks(out, inc, 2), [0, 1])
        adaptive = build_index(out, inc, [0], "adaptive", 2, 4)
        self.assertEqual((adaptive.entries, adaptive.radii, adaptive.build_scans), (3, [(2, 0)], 4))
        self.assertEqual(adaptive.query(1, 0, 1), (True, "upper", 0))
        self.assertEqual(adaptive.query(0, 2, 1)[0:2], (True, "fallback"))
        with self.assertRaises(IndexBudgetError) as error:
            build_index(out, inc, [0], "uniform", 2, 4)
        self.assertEqual(error.exception.build_scans, 4)

    def test_negative_certificate_and_exact_boundary(self):
        out, inc = graph(5, [(0, 1), (1, 2), (2, 3)])
        idx = build_index(out, inc, [0], "uniform", 2, 10)
        self.assertEqual(idx.query(1, 4, 1), (False, "lower", 0))
        self.assertEqual(idx.query(1, 3, 2)[0:2], (True, "fallback"))
        self.assertEqual(idx.query(0, 2, 2), (True, "upper", 0))
        for mode in ("uniform", "adaptive"):
            with self.assertRaises(IndexBudgetError):
                build_index(out, inc, [0], mode, 1, 1)
        empty = build_index(out, inc, [], "adaptive", 3, 0)
        self.assertEqual(empty.entries, 0)
        self.assertEqual(empty.query(0, 3, 3)[0:2], (True, "fallback"))


if __name__ == "__main__":
    unittest.main()
