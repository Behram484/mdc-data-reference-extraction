"""Loading and describing the competition data.

Nothing here knows about extraction -- it only answers "what is on disk"
and "what does train_labels.csv say".
"""

from __future__ import annotations

import csv
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# "Missing" appears in train_labels.csv as a *type*, alongside Primary and
# Secondary -- never as a dataset_id (verified: 347 rows, 0 of them in the
# dataset_id column). It marks a candidate id that the annotators found in the
# text and then rejected as not being a data citation.
#
# Two consequences, both load-bearing:
#   1. These rows never enter the gold set. A submission may only contain
#      Primary/Secondary, so an (article, dataset, "Missing") triple is
#      unmatchable by construction.
#   2. The 309 articles that carry only Missing rows are the true negatives.
#      Any prediction for them is a false positive.
#
# The rejected dataset_ids are also the best false-positive catalogue in the
# data -- they are precisely the id shapes that look like data citations but
# are not. S3 mines this.
MISSING = "Missing"

VALID_TYPES = ("Primary", "Secondary")


@dataclass(frozen=True)
class Label:
    article_id: str
    dataset_id: str
    type: str

    @property
    def is_missing(self) -> bool:
        """True for a candidate id the annotators rejected. See MISSING above."""
        return self.type == MISSING

    @property
    def triple(self) -> tuple[str, str, str]:
        return (self.article_id, self.dataset_id, self.type)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def load_labels(path: str | os.PathLike) -> list[Label]:
    """Read train_labels.csv into Label rows, whitespace-stripped."""
    rows = _read_csv(Path(path))
    if not rows:
        return []
    missing_cols = {"article_id", "dataset_id", "type"} - set(rows[0])
    if missing_cols:
        raise ValueError(f"{path}: missing column(s) {sorted(missing_cols)}")
    return [
        Label(
            article_id=r["article_id"].strip(),
            dataset_id=r["dataset_id"].strip(),
            type=r["type"].strip(),
        )
        for r in rows
    ]


def gold_triples(labels: list[Label]) -> set[tuple[str, str, str]]:
    """The scoring target: real citations only, deduplicated per article.

    A set does the per-article deduplication for free, which is exactly the
    competition rule (the same (dataset_id, type) inside one article counts once).
    """
    return {lab.triple for lab in labels if not lab.is_missing}


def articles_with_citations(labels: list[Label]) -> set[str]:
    return {lab.article_id for lab in labels if not lab.is_missing}


def all_labelled_articles(labels: list[Label]) -> set[str]:
    return {lab.article_id for lab in labels}


def discover_articles(directory: str | os.PathLike, suffix: str) -> dict[str, Path]:
    """Map article_id -> file path for every ``*.{suffix}`` in ``directory``.

    The article_id is the filename stem, which is how the competition links
    train/XML/<id>.xml to the article_id column in train_labels.csv.
    """
    d = Path(directory)
    if not d.is_dir():
        return {}
    return {p.stem: p for p in sorted(d.glob(f"*.{suffix.lstrip('.')}"))}


def describe_labels(labels: list[Label]) -> dict[str, object]:
    """Summary numbers used by scripts/inspect_data.py and by the README."""
    real = [lab for lab in labels if not lab.is_missing]
    missing = [lab for lab in labels if lab.is_missing]
    per_article = Counter(lab.article_id for lab in real)
    return {
        "rows": len(labels),
        "real_rows": len(real),
        "missing_rows": len(missing),
        "unique_triples": len(gold_triples(labels)),
        "articles_total": len(all_labelled_articles(labels)),
        "articles_with_citations": len(per_article),
        "articles_without_citations": len(
            all_labelled_articles(labels) - set(per_article)
        ),
        "type_counts": dict(Counter(lab.type for lab in labels).most_common()),
        "max_citations_per_article": max(per_article.values(), default=0),
        "mean_citations_per_citing_article": (
            round(sum(per_article.values()) / len(per_article), 2) if per_article else 0.0
        ),
    }
