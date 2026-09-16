"""Deciding Primary vs Secondary.

Three signals survived article-grouped cross-validation inside dev. Accuracy is
measured on correctly-extracted mentions, so it reflects the classifier alone:

    always Secondary (majority)   67.6%
    format prior (S2/S3)          86.1%
    format + location             88.9%
    + repository prefix           89.4%

Grouping the folds by article is not a detail. Mentions are not independent --
one paper contributes dozens of ids sharing the same surrounding text -- so
ungrouped folds let a model recognise the *article* and score far higher than
it deserves. Mining n-grams under ungrouped folds surfaced "duck egypt" and
"flagellar" as top predictors, which is article identity, not language.

Context keywords are deliberately absent. They were the planned approach and
they do not work here: of the intuitive lexicon, "data generated for this
study", "we deposited", "were generated", "previously published" and "reused"
never appear in a single dev context, while "publicly available" and "available
from" -- both supposedly Secondary cues -- run 86% and 70% *Primary*. The best
cue variant was worth +0.15pp against a seed-to-seed standard deviation of
0.5-0.7pp, i.e. noise, and most variants made the rule worse.
"""

from __future__ import annotations

import os
from pathlib import Path

from mdc.context import Evidence
from mdc.repositories import doi_prefix
from mdc.xmltext import REFERENCES

PRIMARY = "Primary"
SECONDARY = "Secondary"

_PREFIX_TYPES_PATH = Path(__file__).resolve().parents[2] / "models" / "doi_prefix_types.txt"


def load_prefix_types(path: str | os.PathLike | None = None) -> dict[str, str]:
    """prefix -> majority type, learned from dev. Empty if never generated."""
    p = Path(path) if path else _PREFIX_TYPES_PATH
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].strip()
        if not token:
            continue
        prefix, _, ty = token.partition(" ")
        if prefix and ty.strip() in (PRIMARY, SECONDARY):
            out[prefix] = ty.strip()
    return out


def format_location_type(evidence: Evidence) -> str:
    """The rule without any learned parameter: 88.9% on dev.

    A DOI found only in the bibliography is someone else's dataset 60% of the
    time; one in the main text is the article's own 88% of the time.
    """
    if evidence.location == REFERENCES:
        return SECONDARY
    return PRIMARY if doi_prefix(evidence.dataset_id) else SECONDARY


def classify(evidence: Evidence, prefix_types: dict[str, str] | None = None) -> str:
    """Primary or Secondary for one mention: 89.4% on dev.

    A repository's own habits beat the generic rule where they are known --
    Dryad deposits are the article's own data 96% of the time, GBIF downloads
    are someone else's -- so a prefix with enough evidence overrides.
    """
    types = load_prefix_types() if prefix_types is None else prefix_types
    prefix = doi_prefix(evidence.dataset_id)
    if prefix and prefix in types:
        return types[prefix]
    return format_location_type(evidence)
