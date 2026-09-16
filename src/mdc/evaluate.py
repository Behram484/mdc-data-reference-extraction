"""Scoring: micro-averaged precision / recall / F1 over (article_id, dataset_id, type).

Deliberately a dumb exact-string matcher, mirroring the Kaggle metric. All
normalisation (DOI casing, trailing punctuation, url prefixes) belongs in the
prediction pipeline, not here -- otherwise the scorer would paper over exactly
the bugs S3 is meant to surface.
"""

from __future__ import annotations

import csv
import os
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path

Triple = tuple[str, str, str]


@dataclass(frozen=True)
class Score:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    n_pred: int
    n_gold: int

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"P {self.precision:.4f}  R {self.recall:.4f}  F1 {self.f1:.4f}   "
            f"(tp={self.tp} fp={self.fp} fn={self.fn}; "
            f"pred={self.n_pred} gold={self.n_gold})"
        )


def score(gold: set[Triple], pred: set[Triple]) -> Score:
    tp = len(gold & pred)
    fp = len(pred - gold)
    fn = len(gold - pred)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return Score(precision, recall, f1, tp, fp, fn, len(pred), len(gold))


def restrict(triples: set[Triple], article_ids: set[str]) -> set[Triple]:
    """Keep only triples belonging to the evaluated split."""
    return {t for t in triples if t[0] in article_ids}


def score_on_split(
    gold: set[Triple], pred: set[Triple], article_ids: set[str]
) -> tuple[Score, int]:
    """Score within one split; also report predictions that fell outside it.

    Predictions for articles outside the split are dropped rather than counted
    as false positives -- they are a caller bug, not a model error, so the
    count is returned separately for the caller to warn about.
    """
    out_of_split = len(pred) - len(restrict(pred, article_ids))
    return score(restrict(gold, article_ids), restrict(pred, article_ids)), out_of_split


def per_type_scores(gold: set[Triple], pred: set[Triple]) -> dict[str, Score]:
    """Break the score down by Primary / Secondary.

    Useful from S4 onwards: a classifier that predicts Primary for everything
    still looks fine overall while being useless on Secondary.
    """
    types = {t[2] for t in gold} | {t[2] for t in pred}
    return {
        ty: score({t for t in gold if t[2] == ty}, {t for t in pred if t[2] == ty})
        for ty in sorted(types)
    }


def type_confusion(gold: set[Triple], pred: set[Triple]) -> dict[str, int]:
    """Where a (article, dataset) pair was found but the type was wrong.

    Splits the false positives into "wrong type" (the mention was located, the
    Primary/Secondary call was wrong) and "spurious" (the mention is not a real
    citation at all). Those two failures need completely different fixes.
    """
    gold_pairs = {(a, d): ty for a, d, ty in gold}
    counts: Counter[str] = Counter()
    for a, d, ty in pred - gold:
        gold_ty = gold_pairs.get((a, d))
        if gold_ty is None:
            counts["spurious_mention"] += 1
        else:
            counts[f"{gold_ty}->{ty}"] += 1
    return dict(counts.most_common())


def load_predictions(path: str | os.PathLike) -> set[Triple]:
    """Read a prediction CSV. Accepts the Kaggle layout with or without row_id."""
    with open(Path(path), "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return set()
        missing = {"article_id", "dataset_id", "type"} - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{path}: missing column(s) {sorted(missing)}")
        return {
            (r["article_id"].strip(), r["dataset_id"].strip(), r["type"].strip())
            for r in reader
        }


def write_predictions(path: str | os.PathLike, triples: set[Triple]) -> None:
    """Write predictions in Kaggle's submission layout (row_id first)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["row_id", "article_id", "dataset_id", "type"])
        for i, (article_id, dataset_id, ty) in enumerate(sorted(triples)):
            writer.writerow([i, article_id, dataset_id, ty])
