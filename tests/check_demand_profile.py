"""Review local receipts for the completed demand-profile experiment."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/adaptive-radius/demand-profile"
BUILDERS = ("adaptive-full", "adaptive-global", "adaptive-demand")


def read_rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_answers(queries, answers, expected_count):
    assert len(queries) == len(answers) == expected_count
    for query, answer in zip(queries, answers):
        truth = int(0 <= int(query["d"]) <= int(query["k"]))
        assert int(answer["yes"]) == truth, query


def main():
    construction = read_rows(OUTPUT / "construction.tsv")
    deployments = read_rows(OUTPUT / "main.tsv")
    transfer = read_rows(OUTPUT / "transfer.tsv")

    assert len(construction) == 90 and len(deployments) == 200 and len(transfer) == 75
    assert Counter(row["load"] for row in deployments) == {"mixed": 175, "k4": 25}
    assert len({(row["graph"], row["method"], row["pair"]) for row in construction}) == 90
    assert len({(row["graph"], row["load"], row["method"], row["pair"]) for row in deployments}) == 200
    assert len({(row["split"], row["method"], row["pair"]) for row in transfer}) == 75
    assert all(row["candidate_equivalent"] == "True" for row in construction)
    assert sum(int(row["mismatches"]) for row in deployments + transfer) == 0

    receipts = list(OUTPUT.rglob("receipt.json"))
    assert len(receipts) == 90 + 18 + 160 + 200 + 75
    for path in receipts:
        receipt = json.loads(path.read_text())
        for name, expected in receipt["files"].items():
            assert digest(path.parent / name) == expected, (path, name)

    for graph in {row["graph"] for row in construction}:
        rows = [row for row in construction if row["graph"] == graph]
        identities = {(row["config_sha256"], row["candidate_sha256"], row["table_sha256"],
                       row["index_bytes"]) for row in rows}
        assert len(identities) == 1
        details = [digest(OUTPUT / "construction" / graph / method / "pair-1/query/details.tsv")
                   for method in BUILDERS]
        assert len(set(details)) == 1

    frozen = json.loads((OUTPUT / "frozen.json").read_text())
    assert len(frozen) == 200
    for row in deployments:
        key = f'{row["load"]}/{row["graph"]}/{row["method"]}/pair-{row["pair"]}'
        fit = frozen[key]
        assert row["config_sha256"] == fit["config_sha256"]
        assert row["table_sha256"] == fit["table_sha256"]
        query_file = ROOT / "dataset/workloads" / row["graph"] / "benchmark.tsv"
        queries = read_rows(query_file)
        if row["load"] == "k4":
            queries = [query for query in queries if query["k"] == "4"]
        answers = read_rows(OUTPUT / "deploy" / key / "query/answers.tsv")
        verify_answers(queries, answers, int(row["queries"]))

    workload = OUTPUT / "workloads/email-EuAll"
    for row in transfer:
        query_file = workload / (row["split"] + ".tsv")
        assert digest(query_file) == row["query_sha256"]
        answers = read_rows(OUTPUT / "transfer" / row["split"] / row["method"] /
                            f'pair-{row["pair"]}' / "answers.tsv")
        verify_answers(read_rows(query_file), answers, int(row["queries"]))

    manifest = json.loads((workload / "manifest.json").read_text())
    used = set(map(int, (workload / "excluded.txt").read_text().split()))
    for split, record in manifest["splits"].items():
        query_file = workload / (split + ".tsv")
        assert digest(query_file) == record["sha256"]
        sources = {int(row["s"]) for row in read_rows(query_file)}
        assert not (used & sources)
        used.update(sources)

    assert len(read_rows(OUTPUT / "historical.tsv")) == 63
    assert len(read_rows(OUTPUT / "summary.tsv")) == 40
    assert len(read_rows(OUTPUT / "transfer-combined.tsv")) == 25
    assert not list(OUTPUT.rglob("*.pending"))
    print("fixed construction records:", len(construction), "main records:", len(deployments),
          "transfer records:", len(transfer))
    print("verified process receipts:", len(receipts))
    print("main decisions:", sum(int(row["queries"]) for row in deployments),
          "transfer decisions:", sum(int(row["queries"]) for row in transfer))
    print("zero mismatches, all SHA-256 receipts verified")


if __name__ == "__main__":
    main()
