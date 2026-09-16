"""The null baseline: predict nothing at all.

Exists to prove the pipeline is wired end to end before any extraction logic
lands. Correct behaviour is F1 = 0.0000 with fp = 0 and fn = every gold triple.

    python scripts/predict_empty.py --out outputs/empty.csv
"""

from __future__ import annotations

import argparse

import _paths  # noqa: F401

from mdc.evaluate import write_predictions


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="outputs/empty.csv")
    args = ap.parse_args()
    write_predictions(args.out, set())
    print(f"wrote 0 predictions to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
