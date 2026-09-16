"""Write the dev / holdout article-id lists.

    python scripts/make_split.py --data-dir data

Split covers every labelled article, including the ones with no citation --
those are the true negatives that keep precision honest.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import _paths  # noqa: F401

from mdc.data import all_labelled_articles, articles_with_citations, load_labels
from mdc.split import (
    DEFAULT_DEV_FRACTION,
    DEFAULT_SEED,
    stratified_split_articles,
    write_split,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=os.environ.get("MDC_DATA_DIR", "data"))
    ap.add_argument("--out-dir", default="splits", help="committed to git; ids only")
    ap.add_argument("--dev-fraction", type=float, default=DEFAULT_DEV_FRACTION)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args()

    labels_path = Path(args.data_dir) / "train_labels.csv"
    if not labels_path.exists():
        print(f"!! {labels_path} not found")
        return 1

    labels = load_labels(labels_path)
    articles = all_labelled_articles(labels)
    citing = articles_with_citations(labels)

    dev, holdout = stratified_split_articles(
        citing, articles - citing, args.dev_fraction, args.seed
    )
    out = Path(args.out_dir)
    write_split(out / "dev.txt", dev)
    write_split(out / "holdout.txt", holdout)

    print(f"seed={args.seed}  dev_fraction={args.dev_fraction}")
    for name, ids in (("dev", dev), ("holdout", holdout)):
        n_citing = len(set(ids) & citing)
        share = n_citing / len(ids) if ids else 0.0
        print(f"  {name:<8} {len(ids):>6} articles   {n_citing} citing ({share:.1%})")
    print(f"  overlap  {len(set(dev) & set(holdout))} (must be 0)")
    print(f"  written  {out / 'dev.txt'}, {out / 'holdout.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
