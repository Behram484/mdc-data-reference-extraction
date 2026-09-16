"""Turning one article into a set of predicted data citations.

Shared by every stage from S1 onwards so that a stage differs from the one
before it only in configuration, never in a reimplementation of the same walk.
"""

from __future__ import annotations

import os
from pathlib import Path

from mdc.accessions import Pattern, SELECTED, find_accessions
from mdc.dois import article_id_to_doi, drop_self_citations, find_dois
from mdc.repositories import allowed_prefixes, is_data_doi
from mdc.xmltext import (
    MAIN,
    REFERENCES,
    parse_segments,
    section_text,
    self_doi_candidates,
)

PRIMARY = "Primary"
SECONDARY = "Secondary"


def extract_ids(
    path: str | os.PathLike,
    article_id: str,
    sections: set[str] | None = None,
    patterns: tuple[Pattern, ...] = SELECTED,
    exclude_self: bool = True,
    filter_doi_prefix: bool = True,
    read_references: bool = False,
) -> set[str]:
    """Every dataset id this article cites, DOIs normalised, accessions verbatim.

    ``read_references`` mines the bibliography as well. That is only safe with
    ``filter_doi_prefix`` on: read wholesale the reference list contributes 47
    true mentions and 11,775 false ones, but restricted to allowed repository
    prefixes it yields 62 true and 29 false. Data citations formatted as
    bibliography entries are common enough to be worth reaching for -- but only
    through that filter.

    Delegates to collect_evidence so the two entry points cannot drift: they
    previously disagreed about whether accession IDs are scanned in the
    bibliography, which silently changed the prediction set depending on which
    one the caller used.
    """
    from mdc.context import collect_evidence

    return set(
        collect_evidence(
            path,
            article_id,
            patterns=patterns,
            filter_doi_prefix=filter_doi_prefix,
            read_references=read_references,
            exclude_self=exclude_self,
            sections=sections,
        )
    )


def format_prior_type(dataset_id: str) -> str:
    """Guess Primary/Secondary from the shape of the id alone.

    Not a classifier -- a measured prior. In the training labels DOI citations
    run 215 Primary / 110 Secondary while accession IDs run 339 Secondary /
    55 Primary, which is ~77% accuracy from format alone. S4 has to beat this
    to be worth anything, so it is what S2 and S3 emit.
    """
    return PRIMARY if dataset_id.startswith("https://doi.org/") else SECONDARY
