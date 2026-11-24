"""Check raw-to-dense orientation, duplicates and explicitly declared isolates."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class NormalizeTest(unittest.TestCase):
    def test_input_formats(self):
        sources = [
            ("edges", "# native IDs\n10\t50\n50\t50\n10\t50\n", 2, "10 50"),
            ("gra", "graph_for_greach\n3\n0: 1 1 #\n1: 1 #\n2: #\n", 3, "0 1 2"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "normalize"
            subprocess.run(["g++", "-std=c++17", "-O2", Path(__file__).with_name("normalize_large.cpp"),
                            "-o", binary], check=True)
            for fmt, source, n, ids in sources:
                with self.subTest(fmt=fmt):
                    run = subprocess.run([binary, fmt, "3", root/"edges", root/"nodes"], input=source,
                                         text=True, capture_output=True, check=True)
                    self.assertEqual(run.stdout.split(), [str(n), "3", "2", "1", str(n-2)])
                    self.assertEqual((root/"edges").read_text(), "0\t1\n1\t1\n")
                    mapping = [row.split("\t")[1] for row in (root/"nodes").read_text().splitlines()[1:]]
                    self.assertEqual(mapping, ids.split())


if __name__ == "__main__":
    unittest.main()
