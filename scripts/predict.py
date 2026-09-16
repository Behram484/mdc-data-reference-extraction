"""Rule-based prediction over the training articles.

Stages are configurations of this one script, so their numbers are comparable:

    S1  python scripts/predict.py --patterns none --type-rule constant
    S2  python scripts/predict.py --patterns selected

    --patterns    none | selected | core | risky | all | <comma-separated names>
    --sections    main | main,references
    --type-rule   format (DOI->Primary, accession->Secondary) | constant
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import _paths  # noqa: F401

from mdc.accessions import resolve
from mdc.data import all_labelled_articles, discover_articles, load_labels
from mdc.evaluate import write_predictions
from mdc.classify import classify, format_location_type, load_prefix_types
from mdc.context import collect_evidence
from mdc.pipeline import PRIMARY, extract_ids, format_prior_type
from mdc.split import read_split
from mdc.xmltext import MAIN


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=os.environ.get("MDC_DATA_DIR", "data"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="")
    ap.add_argument("--patterns", default="selected")
    ap.add_argument("--sections", default=MAIN)
    ap.add_argument(
        "--type-rule",
        default="evidence",
        choices=["evidence", "format_location", "format", "constant"],
        help="evidence = location + repository prefix (S4); format = the S2/S3 prior",
    )
    ap.add_argument("--constant-type", default=PRIMARY)
    ap.add_argument("--keep-self-doi", action="store_true")
    ap.add_argument("--no-prefix-filter", action="store_true",
                    help="ablation: keep DOIs from any registrant, not just data repositories")
    ap.add_argument("--read-references", action="store_true",
                    help="also mine the bibliography (only safe with the prefix filter on)")
    args = ap.parse_args()

    root = Path(args.data_dir)
    sections = {s.strip() for s in args.sections.split(",") if s.strip()}
    patterns = resolve(args.patterns)

    labels = load_labels(root / "train_labels.csv")
    articles = all_labelled_articles(labels)
    if args.split:
        articles &= read_split(args.split)
    xml = discover_articles(root / "train" / "XML", "xml")

    uses_evidence = args.type_rule in ("evidence", "format_location")
    prefix_types = load_prefix_types() if args.type_rule == "evidence" else {}

    triples: set[tuple[str, str, str]] = set()
    n_xml = 0
    for article_id in sorted(articles):
        path = xml.get(article_id)
        if path is None:
            continue
        n_xml += 1

        if uses_evidence:
            evidence = collect_evidence(
                path,
                article_id,
                patterns,
                filter_doi_prefix=not args.no_prefix_filter,
                read_references=args.read_references,
            )
            for dataset_id, ev in evidence.items():
                ty = (
                    classify(ev, prefix_types)
                    if args.type_rule == "evidence"
                    else format_location_type(ev)
                )
                triples.add((article_id, dataset_id, ty))
            continue

        for dataset_id in extract_ids(
            path,
            article_id,
            sections,
            patterns,
            exclude_self=not args.keep_self_doi,
            filter_doi_prefix=not args.no_prefix_filter,
            read_references=args.read_references,
        ):
            ty = (
                format_prior_type(dataset_id)
                if args.type_rule == "format"
                else args.constant_type
            )
            triples.add((article_id, dataset_id, ty))

    write_predictions(args.out, triples)
    print(f"articles {len(articles)} ({n_xml} with XML) | sections {sorted(sections)}")
    print(f"patterns {len(patterns)}: {[p.name for p in patterns] or 'none (DOI only)'}")
    print(f"type rule {args.type_rule} | prefix filter "
          f"{'off' if args.no_prefix_filter else 'on'} | references "
          f"{'read' if args.read_references else 'skipped'}")
    print(f"wrote {len(triples)} predictions -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
