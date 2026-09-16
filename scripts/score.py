"""Score a prediction CSV against train_labels.csv on one split.

    python scripts/score.py --pred outputs/empty.csv --split splits/dev.txt
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _paths  # noqa: F401

from mdc.data import gold_triples, load_labels
from mdc.evaluate import (
    load_predictions,
    per_type_scores,
    restrict,
    score_on_split,
    type_confusion,
)
from mdc.split import read_split


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred", required=True, help="CSV with article_id,dataset_id,type")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--split", default="splits/dev.txt")
    ap.add_argument("--label", default="", help="stage name, e.g. 'S1 DOI regex'")
    ap.add_argument("--json-out", default="", help="also append the score as JSON lines")
    args = ap.parse_args()

    labels = load_labels(Path(args.data_dir) / "train_labels.csv")
    gold = gold_triples(labels)
    pred = load_predictions(args.pred)
    article_ids = read_split(args.split)

    result, out_of_split = score_on_split(gold, pred, article_ids)
    if out_of_split:
        print(f"!! {out_of_split} predicted rows are for articles outside {args.split}; ignored")

    name = args.label or Path(args.pred).stem
    print(f"\n{name}  on {Path(args.split).stem} ({len(article_ids)} articles)")
    print(f"  {result}")

    g = restrict(gold, article_ids)
    p = restrict(pred, article_ids)
    if p:
        print("\n  by type:")
        for ty, s in per_type_scores(g, p).items():
            print(f"    {ty:<10} {s}")
        confusion = type_confusion(g, p)
        if confusion:
            print("\n  false positives by cause:")
            for cause, n in confusion.items():
                print(f"    {cause:<22} {n}")

    print("\n  markdown row:")
    print(
        f"  | {name} | {result.precision:.4f} | {result.recall:.4f} | {result.f1:.4f} |"
    )

    if args.json_out:
        record = {"stage": name, "split": Path(args.split).stem, **result.as_dict()}
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        print(f"\n  appended to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
