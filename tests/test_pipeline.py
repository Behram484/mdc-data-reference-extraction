"""End-to-end S0 check on a synthetic mini-dataset.

Runs without the 2 GB download: builds a fake data dir in a temp folder, then
drives make_split.py / predict_empty.py / score.py as subprocesses exactly the
way the real pipeline is driven.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mdc.data import describe_labels, gold_triples, load_labels  # noqa: E402
from mdc.evaluate import score  # noqa: E402
from mdc.split import split_articles  # noqa: E402


def build_fixture(root: Path, n_articles: int = 40) -> None:
    """20 citing articles (1-3 citations each) + 20 with none."""
    (root / "train" / "XML").mkdir(parents=True)
    rows = []
    for i in range(n_articles):
        article_id = f"10.1234_art{i:03d}"
        (root / "train" / "XML" / f"{article_id}.xml").write_text(
            "<article><body><p>text</p></body></article>", encoding="utf-8"
        )
        if i < n_articles // 2:
            for j in range((i % 3) + 1):
                rows.append(
                    {
                        "article_id": article_id,
                        "dataset_id": f"https://doi.org/10.5061/dryad.{i:03d}{j}",
                        "type": "Primary" if j % 2 == 0 else "Secondary",
                    }
                )
        else:
            rows.append(
                {"article_id": article_id, "dataset_id": "Missing", "type": "Missing"}
            )
    with open(root / "train_labels.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["article_id", "dataset_id", "type"])
        w.writeheader()
        w.writerows(rows)


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [sys.executable, *args], cwd=cwd, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise AssertionError(f"{args} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc


class TestScorer(unittest.TestCase):
    def test_empty_prediction_scores_zero(self):
        gold = {("a", "d", "Primary")}
        s = score(gold, set())
        self.assertEqual((s.precision, s.recall, s.f1), (0.0, 0.0, 0.0))
        self.assertEqual((s.tp, s.fp, s.fn), (0, 0, 1))

    def test_perfect_prediction_scores_one(self):
        gold = {("a", "d", "Primary"), ("b", "e", "Secondary")}
        self.assertEqual(score(gold, set(gold)).f1, 1.0)

    def test_wrong_type_is_both_fp_and_fn(self):
        gold = {("a", "d", "Primary")}
        s = score(gold, {("a", "d", "Secondary")})
        self.assertEqual((s.tp, s.fp, s.fn), (0, 1, 1))

    def test_prediction_for_uncited_article_is_a_false_positive(self):
        s = score(set(), {("quiet_article", "d", "Primary")})
        self.assertEqual((s.fp, s.precision), (1, 0.0))


class TestSplit(unittest.TestCase):
    def test_split_is_disjoint_complete_and_deterministic(self):
        ids = {f"a{i}" for i in range(200)}
        dev, hold = split_articles(ids)
        self.assertEqual(set(dev) | set(hold), ids)
        self.assertFalse(set(dev) & set(hold))
        self.assertEqual((dev, hold), split_articles(ids))

    def test_no_article_straddles_the_split(self):
        """The leak the row-level split would cause, asserted directly."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_fixture(root)
            labels = load_labels(root / "train_labels.csv")
            dev, hold = split_articles({lab.article_id for lab in labels})
            dev_set, hold_set = set(dev), set(hold)
            for lab in labels:
                in_dev = lab.article_id in dev_set
                in_hold = lab.article_id in hold_set
                self.assertTrue(
                    in_dev ^ in_hold,
                    f"{lab.article_id}: dev={in_dev} holdout={in_hold}",
                )


class TestEndToEnd(unittest.TestCase):
    def test_empty_baseline_runs_and_scores_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            build_fixture(data)

            labels = load_labels(data / "train_labels.csv")
            desc = describe_labels(labels)
            self.assertEqual(desc["articles_total"], 40)
            self.assertEqual(desc["articles_with_citations"], 20)
            self.assertEqual(desc["articles_without_citations"], 20)
            self.assertEqual(desc["unique_triples"], len(gold_triples(labels)))

            out_dir = Path(tmp) / "out"
            splits = Path(tmp) / "splits"
            run("scripts/inspect_data.py", "--data-dir", str(data), cwd=ROOT)
            run(
                "scripts/make_split.py",
                "--data-dir", str(data),
                "--out-dir", str(splits),
                cwd=ROOT,
            )
            run("scripts/predict_empty.py", "--out", str(out_dir / "empty.csv"), cwd=ROOT)
            proc = run(
                "scripts/score.py",
                "--pred", str(out_dir / "empty.csv"),
                "--data-dir", str(data),
                "--split", str(splits / "dev.txt"),
                "--label", "S0 empty baseline",
                cwd=ROOT,
            )
            self.assertIn("F1 0.0000", proc.stdout)
            self.assertIn("fp=0", proc.stdout)


if __name__ == "__main__":
    unittest.main()
