"""Confidence interval for a score, resampling *articles* rather than mentions.

    python scripts/bootstrap_ci.py --pred outputs/s4_evidence.csv --split splits/dev.txt

Citations inside one paper are not independent observations -- a single article
can contribute 30 mentions that share a repository, a section and a type. The
effective sample size is therefore the number of articles, not the number of
mentions, and any interval computed over mentions will be far too narrow.

Resampling articles with replacement gives an honest interval. On dev it puts
S4 at 0.6392 with a 95% interval of 0.53-0.73 -- an uncertainty of +-0.10 that
a mention-level interval would have hidden entirely.
"""

from __future__ import annotations

import argparse
import os
import random
from collections import defaultdict
from pathlib import Path

import _paths  # noqa: F401

from mdc.data import gold_triples, load_labels
from mdc.evaluate import load_predictions, mentions, score
from mdc.split import read_split


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=os.environ.get("MDC_DATA_DIR", "data"))
    ap.add_argument("--pred", required=True)
    ap.add_argument("--split", default="splits/dev.txt")
    ap.add_argument("--resamples", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--mention-level", action="store_true")
    args = ap.parse_args()

    split = sorted(read_split(args.split))
    labels = load_labels(Path(args.data_dir) / "train_labels.csv")
    gold = {t for t in gold_triples(labels) if t[0] in split}
    pred = {t for t in load_predictions(args.pred) if t[0] in split}
    if args.mention_level:
        gold = {(a, d, "") for a, d in mentions(gold)}
        pred = {(a, d, "") for a, d in mentions(pred)}

    by_article_gold: defaultdict[str, set] = defaultdict(set)
    by_article_pred: defaultdict[str, set] = defaultdict(set)
    for t in gold:
        by_article_gold[t[0]].add(t)
    for t in pred:
        by_article_pred[t[0]].add(t)

    point = score(gold, pred)
    rng = random.Random(args.seed)
    f1s = []
    for _ in range(args.resamples):
        sample = [split[rng.randrange(len(split))] for _ in range(len(split))]
        g: set = set()
        p: set = set()
        # tag each draw so the same article drawn twice counts twice
        for i, article_id in enumerate(sample):
            g.update((i,) + t for t in by_article_gold.get(article_id, ()))
            p.update((i,) + t for t in by_article_pred.get(article_id, ()))
        f1s.append(score(g, p).f1)

    f1s.sort()
    lo = f1s[int(0.025 * len(f1s))]
    hi = f1s[int(0.975 * len(f1s))]
    citing = len(by_article_gold)
    print(f"{Path(args.pred).name} on {Path(args.split).stem}")
    print(f"  articles {len(split)} ({citing} with a citation) | gold {len(gold)}")
    print(f"  F1 {point.f1:.4f}")
    print(f"  95% interval over articles: {lo:.4f} - {hi:.4f}  (width {hi - lo:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
