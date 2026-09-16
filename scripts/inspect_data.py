"""Report what is actually on disk, before we trust any of it.

    python scripts/inspect_data.py --data-dir data
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from pathlib import Path

import _paths  # noqa: F401  (sys.path side effect)

from mdc.data import (
    articles_with_citations,
    describe_labels,
    discover_articles,
    load_labels,
)

SUBDIRS = [
    ("train/XML", "xml"),
    ("train/PDF", "pdf"),
    ("test/XML", "xml"),
    ("test/PDF", "pdf"),
]


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def shape_of(dataset_id: str) -> str:
    """Collapse an id to a coarse shape so the format mix is readable at a glance."""
    s = dataset_id.strip()
    if re.match(r"^https?://(dx\.)?doi\.org/", s, re.I):
        return "doi-url"
    if re.match(r"^10\.\d{4,}/", s):
        return "doi-bare"
    m = re.match(r"^([A-Za-z]+)[-_]?\d", s)
    if m:
        return f"accession:{m.group(1).upper()}"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=os.environ.get("MDC_DATA_DIR", "data"), help="root holding train/, test/, *.csv")
    args = ap.parse_args()

    root = Path(args.data_dir).expanduser().resolve()
    print(f"data root: {root}")
    if not root.is_dir():
        print("  !! not a directory -- point --data-dir at the unzipped Kaggle data")
        return 1

    print("\n--- top level ---")
    for entry in sorted(root.iterdir()):
        kind = "dir " if entry.is_dir() else "file"
        size = "" if entry.is_dir() else f"  {human_bytes(entry.stat().st_size)}"
        print(f"  {kind} {entry.name}{size}")

    print("\n--- article files ---")
    found: dict[str, dict[str, Path]] = {}
    for rel, suffix in SUBDIRS:
        d = root / rel
        arts = discover_articles(d, suffix)
        found[rel] = arts
        total = sum(p.stat().st_size for p in arts.values())
        state = "MISSING" if not d.is_dir() else f"{len(arts):>6} files  {human_bytes(total)}"
        print(f"  {rel:<12} {state}")
        if arts:
            first = next(iter(arts))
            print(f"               example article_id: {first}")

    for prefix in ("train", "test"):
        xml = set(found.get(f"{prefix}/XML", {}))
        pdf = set(found.get(f"{prefix}/PDF", {}))
        if not (xml or pdf):
            continue
        union = xml | pdf
        print(
            f"  {prefix}: {len(union)} articles | XML {len(xml)} "
            f"({len(xml) / len(union):.1%}) | PDF-only {len(pdf - xml)}"
        )

    labels_path = root / "train_labels.csv"
    if not labels_path.exists():
        print("\n--- train_labels.csv --- MISSING")
        return 1

    labels = load_labels(labels_path)
    print("\n--- train_labels.csv ---")
    for key, value in describe_labels(labels).items():
        print(f"  {key:<34} {value}")

    print("\n  dataset_id shapes:")
    for shape, n in Counter(shape_of(lab.dataset_id) for lab in labels).most_common(15):
        print(f"    {shape:<22} {n}")

    print("\n  first 8 rows:")
    for lab in labels[:8]:
        print(f"    {lab.article_id:<32} {lab.dataset_id:<46} {lab.type}")

    train_xml = set(found.get("train/XML", {}))
    if train_xml:
        citing = articles_with_citations(labels)
        print("\n--- label / file coverage ---")
        labelled = {lab.article_id for lab in labels}
        print(f"  labelled articles with XML on disk   {len(labelled & train_xml)}")
        print(f"  labelled articles without XML        {len(labelled - train_xml)}")
        print(f"  XML files with no label row          {len(train_xml - labelled)}")
        print(f"  citing articles reachable via XML    {len(citing & train_xml)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
