"""Article-level dev / holdout split.

Splitting on rows would leak: two citations from the same paper share the same
full text, so a row-level split lets a model see the answer for a paper it is
then scored on. Everything here therefore partitions article_ids.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

DEFAULT_SEED = 42
DEFAULT_DEV_FRACTION = 0.8


def split_articles(
    article_ids: set[str],
    dev_fraction: float = DEFAULT_DEV_FRACTION,
    seed: int = DEFAULT_SEED,
) -> tuple[list[str], list[str]]:
    """Partition article_ids into (dev, holdout).

    Sorted before shuffling so the result depends only on the seed and the id
    set, never on filesystem or dict ordering.
    """
    if not 0.0 < dev_fraction < 1.0:
        raise ValueError(f"dev_fraction must be in (0, 1), got {dev_fraction}")
    ordered = sorted(article_ids)
    random.Random(seed).shuffle(ordered)
    cut = round(len(ordered) * dev_fraction)
    return sorted(ordered[:cut]), sorted(ordered[cut:])


def stratified_split_articles(
    citing: set[str],
    non_citing: set[str],
    dev_fraction: float = DEFAULT_DEV_FRACTION,
    seed: int = DEFAULT_SEED,
) -> tuple[list[str], list[str]]:
    """Split citing and non-citing articles separately, then merge.

    Only 214 of 523 articles carry a citation, so an unstratified draw leaves a
    noticeably different citing-rate in each half (42.1% vs 36.2% at seed 42).
    That shifts the achievable precision between dev and holdout and would make
    stage-to-stage comparisons harder to read than they need to be.
    """
    overlap = citing & non_citing
    if overlap:
        raise ValueError(f"article(s) in both strata: {sorted(overlap)[:3]}")
    dev_a, hold_a = split_articles(citing, dev_fraction, seed)
    # offset the seed so the two strata are not shuffled in lockstep
    dev_b, hold_b = split_articles(non_citing, dev_fraction, seed + 1)
    return sorted(dev_a + dev_b), sorted(hold_a + hold_b)


def write_split(path: str | os.PathLike, article_ids: list[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(article_ids) + "\n", encoding="utf-8")


def read_split(path: str | os.PathLike) -> set[str]:
    text = Path(path).read_text(encoding="utf-8")
    return {line.strip() for line in text.splitlines() if line.strip()}
