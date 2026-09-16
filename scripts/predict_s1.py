"""S1: parse the full-text XML and extract DOIs with a regex.

    python scripts/predict_s1.py --out outputs/s1_doi.csv

Scope is deliberately narrow: DOIs only (accession IDs are S2), and a constant
type (a real classifier is S4). What it measures is how much of the task plain
DOI extraction reaches, and how much the reference-list exclusion is worth.

Type constant: Primary. Among gold DOI citations the split is 215 Primary /
110 Secondary, so Primary is the majority *for this subset* -- even though
Secondary wins overall (449/270), a skew driven entirely by accession IDs.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import _paths  # noqa: F401

from mdc.data import all_labelled_articles, discover_articles, load_labels
from mdc.dois import article_id_to_doi, drop_self_citations, find_dois
from mdc.evaluate import write_predictions
from mdc.split import read_split
from mdc.xmltext import MAIN, REFERENCES, parse_segments, section_text, self_doi_candidates

DEFAULT_TYPE = "Primary"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=os.environ.get("MDC_DATA_DIR", "data"))
    ap.add_argument("--out", default="outputs/s1_doi.csv")
    ap.add_argument("--split", default="", help="restrict to these articles")
    ap.add_argument("--type", default=DEFAULT_TYPE, choices=["Primary", "Secondary"])
    ap.add_argument(
        "--sections",
        default=MAIN,
        help=f"comma-separated: {MAIN}, {REFERENCES}. Adding references is the ablation.",
    )
    ap.add_argument("--keep-self-doi", action="store_true",
                    help="ablation: do not exclude the article's own DOI")
    args = ap.parse_args()

    root = Path(args.data_dir)
    sections = {s.strip() for s in args.sections.split(",") if s.strip()}

    labels = load_labels(root / "train_labels.csv")
    articles = all_labelled_articles(labels)
    if args.split:
        articles &= read_split(args.split)
    xml = discover_articles(root / "train" / "XML", "xml")

    triples: set[tuple[str, str, str]] = set()
    n_xml = n_self_dropped = 0
    for article_id in sorted(articles):
        path = xml.get(article_id)
        if path is None:
            continue
        n_xml += 1
        found = find_dois(section_text(parse_segments(path), sections))
        if not args.keep_self_doi:
            self_dois = self_doi_candidates(path) | {article_id_to_doi(article_id)}
            kept = drop_self_citations(found, self_dois)
            n_self_dropped += len(found) - len(kept)
            found = kept
        triples.update((article_id, doi, args.type) for doi in found)

    write_predictions(args.out, triples)
    print(f"articles considered      {len(articles)}")
    print(f"  with XML on disk       {n_xml}")
    print(f"sections read            {sorted(sections)}")
    print(f"self-DOI mentions droppd {n_self_dropped}")
    print(f"predictions written      {len(triples)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
