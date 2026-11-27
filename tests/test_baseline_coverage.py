"""Check source precedence, exactness and capacity evidence in the coverage list."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from baseline_coverage import combine


def table(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w") as out:
        writer=csv.DictWriter(out,fieldnames=fields,delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


class BaselineCoverageTest(unittest.TestCase):
    def test_three_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for path in ("standard-small/receipt.json","historical-core/receipt.json","pressure/raw.json"):
                target=root/path
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text("{}")
            common=dict(method="bibfs",status="verified",expected="3",checked="3",
                        mismatches="0",graph_sha256="g",query_sha256="q",receipt="receipt.json")
            main=dict(common,graph="small",run="standard-small")
            prior=dict(main,run="historical-core")
            big=dict(prior,graph="large",method="kreach-6",status="capacity_proved")
            pressure=dict(big,status="physical_capacity_proved",receipt="",lower_bytes="100",physical_memory_bytes="50")
            pending=dict(big,method="pll",status="capacity_proved")
            retry=dict(pending,status="verified",receipt="raw.json",run="")
            table(root/"performance.tsv",[main])
            table(root/"historical/performance.tsv",[prior,big,pending])
            table(root/"pressure/reviewed_performance.tsv",[pressure,retry])
            table(root/"historical/kreach-capacity.tsv",[
                dict(graph="large",k="6",payload_lower_bytes="100")
            ])
            result={(r["graph"],r["method"]):r for r in combine(root)}
            self.assertEqual(result["small","bibfs"]["receipt"],"standard-small/receipt.json")
            self.assertEqual(result["large","kreach-6"]["receipt"],"historical/kreach-capacity.tsv")
            self.assertEqual(result["large","pll"]["receipt"],"pressure/raw.json")
            self.assertEqual(result["large","pll"]["status"],"verified")
            table(root/"pressure/reviewed_performance.tsv",[dict(pressure,lower_bytes="101"),retry])
            with self.assertRaises(ValueError):
                combine(root)
            table(root/"pressure/reviewed_performance.tsv",[pressure,dict(retry,mismatches="1")])
            with self.assertRaises(ValueError):
                combine(root)


if __name__=="__main__":
    unittest.main()

