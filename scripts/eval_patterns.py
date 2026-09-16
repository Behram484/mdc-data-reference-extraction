"""Per-pattern accuracy for the accession patterns.

    python scripts/eval_patterns.py --split splits/dev.txt

Answers the only question that matters when adding a pattern: what does this
one cost, and what does it buy? Each row is that pattern run alone, so a
pattern that contributes nothing but false positives cannot hide inside the
aggregate score.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import _paths  # noqa: F401

from mdc.accessions import ALL, Pattern
from mdc.dois import article_id_to_doi, drop_self_citations, find_dois
from mdc.evaluate import score
from mdc.xmltext import self_doi_candidates
from mdc.data import discover_articles, gold_triples, load_labels
from mdc.evaluate import mentions
from mdc.split import read_split
from mdc.xmltext import MAIN, parse_segments, section_text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=os.environ.get("MDC_DATA_DIR", "data"))
    ap.add_argument("--split", default="splits/dev.txt")
    ap.add_argument("--sections", default=MAIN)
    ap.add_argument("--cumulative", action="store_true",
                    help="also sweep patterns onto the S1 DOI baseline, best-precision first")
    args = ap.parse_args()

    root = Path(args.data_dir)
    sections = {s.strip() for s in args.sections.split(",") if s.strip()}
    split = read_split(args.split)
    labels = load_labels(root / "train_labels.csv")
    gold = mentions({t for t in gold_triples(labels) if t[0] in split})
    xml = discover_articles(root / "train" / "XML", "xml")

    texts: dict[str, str] = {}
    for article_id in sorted(split):
        path = xml.get(article_id)
        if path is not None:
            texts[article_id] = section_text(parse_segments(path), sections)

    # what each pattern is even trying to find, by its own shape
    addressable = {
        p.name: {g for g in gold if p.regex.fullmatch(g[1])} for p in ALL
    }

    print(f"split {Path(args.split).stem}: {len(split)} articles, "
          f"{len(texts)} with XML, {len(gold)} gold mentions\n")
    header = f"{'pattern':<15}{'repo':<26}{'pred':>7}{'tp':>5}{'fp':>7}{'prec':>8}{'target':>8}{'hit':>7}"
    print(header)
    print("-" * len(header))

    rows: list[tuple[Pattern, int, int, float]] = []
    for p in ALL:
        pred = {
            (article_id, found)
            for article_id, text in texts.items()
            for found in p.regex.findall(text)
        }
        tp = len(pred & gold)
        fp = len(pred - gold)
        precision = tp / len(pred) if pred else 0.0
        target = addressable[p.name]
        hit = len({g for g in target if g in pred}) / len(target) if target else 0.0
        rows.append((p, tp, fp, precision))
        print(
            f"{p.name:<15}{p.repository:<26}{len(pred):>7}{tp:>5}{fp:>7}"
            f"{precision:>8.3f}{len(target):>8}{hit:>7.1%}"
        )

    print("\ntarget = gold mentions in this split whose id matches the pattern's shape")
    print("hit    = share of those the pattern actually found in the text")

    if args.cumulative:
        base = {
            (article_id, doi)
            for article_id, text in texts.items()
            for doi in drop_self_citations(
                find_dois(text),
                self_doi_candidates(xml[article_id]) | {article_id_to_doi(article_id)},
            )
        }
        print()
        print()
        print("cumulative: patterns added to the S1 DOI baseline, best precision first")
        print()
        head = f"{'+ pattern':<17}{'pred':>7}{'tp':>5}{'fp':>7}{'prec':>8}{'rec':>8}{'F1':>8}{'dF1':>8}"
        print(head)
        print("-" * len(head))
        current = set(base)
        s0 = score(gold, current)
        print(f"{'(S1 DOI only)':<17}{len(current):>7}{s0.tp:>5}{s0.fp:>7}"
              f"{s0.precision:>8.3f}{s0.recall:>8.3f}{s0.f1:>8.4f}{'':>8}")
        previous = s0.f1
        for p, tp, fp, precision in sorted(rows, key=lambda r: (-r[3], -r[1])):
            current |= {
                (article_id, found)
                for article_id, text in texts.items()
                for found in p.regex.findall(text)
            }
            sc = score(gold, current)
            print(f"{'+ ' + p.name:<17}{len(current):>7}{sc.tp:>5}{sc.fp:>7}"
                  f"{sc.precision:>8.3f}{sc.recall:>8.3f}{sc.f1:>8.4f}"
                  f"{sc.f1 - previous:>+8.4f}")
            previous = sc.f1
        print()
        print("scored at mention level (type ignored)")

    worst = [r for r in rows if r[3] < 0.05 and r[2] > 20]
    if worst:
        print("\npatterns costing far more than they return (precision < 0.05, fp > 20):")
        for p, tp, fp, precision in sorted(worst, key=lambda r: -r[2]):
            print(f"  {p.name:<15} tp={tp:<4} fp={fp:<6} prec={precision:.3f}  {p.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
