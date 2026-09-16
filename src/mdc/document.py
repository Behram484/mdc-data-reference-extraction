"""Format-agnostic entry point: hand it an article, get segments back."""

from __future__ import annotations

import os
from pathlib import Path

from mdc import xmltext
from mdc.xmltext import Segment


def parse_segments(path: str | os.PathLike) -> list[Segment]:
    """Dispatch on file extension. Unknown extensions yield nothing."""
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        from mdc import pdftext  # lazy: pypdf is optional

        return pdftext.parse_segments(path)
    return xmltext.parse_segments(path)


def self_doi_candidates(path: str | os.PathLike) -> set[str]:
    """Only XML declares the article's own DOI in machine-readable metadata.

    For a PDF there is no such field, so the article_id mapping in
    dois.article_id_to_doi is the only self-citation guard available.
    """
    if Path(path).suffix.lower() == ".pdf":
        return set()
    return xmltext.self_doi_candidates(path)
