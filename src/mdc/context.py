"""Evidence gathered about each mention, for the Primary/Secondary decision.

A citation is Primary when the article produced the data and Secondary when it
reused someone else's, and that distinction lives in the sentence around the
identifier, not in the identifier itself. This module collects what is knowable
about each mention: where in the document it appeared, and the text surrounding
every occurrence.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from mdc.accessions import SELECTED, Pattern, find_accessions_with_spans
from mdc.dois import article_id_to_doi, drop_self_citations, find_dois_with_spans
from mdc.repositories import allowed_prefixes, is_data_doi
from mdc.xmltext import (
    MAIN,
    REFERENCES,
    parse_segments,
    section_text,
    self_doi_candidates,
)

WINDOW = 250

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class Evidence:
    """Everything one article knows about one dataset id."""

    dataset_id: str
    in_main: bool
    in_references: bool
    contexts: tuple[str, ...]

    @property
    def location(self) -> str:
        if self.in_main and self.in_references:
            return "both"
        return MAIN if self.in_main else REFERENCES

    @property
    def joined_context(self) -> str:
        return " ".join(self.contexts).lower()


def _spans(text: str, patterns: tuple[Pattern, ...]) -> list[tuple[str, int, int]]:
    return find_dois_with_spans(text) + find_accessions_with_spans(text, patterns)


def collect_evidence(
    path: str | os.PathLike,
    article_id: str,
    patterns: tuple[Pattern, ...] = SELECTED,
    window: int = WINDOW,
    filter_doi_prefix: bool = True,
    read_references: bool = True,
    exclude_self: bool = True,
    sections: set[str] | None = None,
) -> dict[str, Evidence]:
    """Map dataset_id -> Evidence for one article.

    Mirrors pipeline.extract_ids: the same ids come out, with provenance
    attached. Kept as a separate entry point so the extraction stages stay
    readable and are not paying for context collection they never use.
    """
    segments = parse_segments(Path(path))
    texts = {MAIN: section_text(segments, sections or {MAIN})}
    if read_references:
        texts[REFERENCES] = section_text(segments, {REFERENCES})

    self_dois = self_doi_candidates(path) | {article_id_to_doi(article_id)}
    allowed = allowed_prefixes() if filter_doi_prefix else None

    seen: dict[str, dict] = {}
    for section, text in texts.items():
        for dataset_id, start, end in _spans(text, patterns):
            if dataset_id.startswith("https://doi.org/"):
                if exclude_self and not drop_self_citations({dataset_id}, self_dois):
                    continue
                if allowed is not None and not is_data_doi(dataset_id, allowed):
                    continue
            entry = seen.setdefault(
                dataset_id, {MAIN: False, REFERENCES: False, "contexts": []}
            )
            entry[section] = True
            snippet = text[max(0, start - window) : end + window]
            entry["contexts"].append(_WS.sub(" ", snippet).strip())

    return {
        dataset_id: Evidence(
            dataset_id=dataset_id,
            in_main=entry[MAIN],
            in_references=entry[REFERENCES],
            contexts=tuple(entry["contexts"]),
        )
        for dataset_id, entry in seen.items()
    }
