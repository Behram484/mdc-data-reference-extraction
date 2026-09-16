"""Text extraction from PDF, for the ~24% of articles with no XML.

Deliberately exposes the same ``parse_segments`` -> ``list[Segment]`` contract
as xmltext, tagging main/references, so nothing downstream knows or cares which
format an article arrived in. S3 established that reading a bibliography costs
11,775 false positives for 47 true mentions; a PDF backend that could not make
that split would drag the same cost back in through the side door.

A PDF has no structure to read it from, so the split is heuristic: find the
last line that is nothing but a references heading and treat the rest of the
document as bibliography. "Last" rather than "first" because the phrase also
appears in running text and in a table of contents.

pypdf is imported lazily. The XML path -- 76% of the corpus and every stage up
to S5 -- must keep working when it is not installed.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from mdc.xmltext import MAIN, REFERENCES, Segment

# A line that is only a bibliography heading, optionally numbered.
_REF_HEADING = re.compile(
    r"^[\s\d.]{0,6}(references?(\s+cited)?|bibliography|literature\s+cited"
    r"|works\s+cited|reference\s+list)[\s:.]*$",
    re.IGNORECASE | re.MULTILINE,
)

_WS = re.compile(r"[ \t ]+")

# A DOI or URL broken across a line: "10.5061/dry-\nad.abc" or ".../dry\nad.abc"
_WRAPPED = re.compile(r"(10\.\d{4,9}/\S*?)-?\n\s*(\S)")


def _dewrap(text: str) -> str:
    """Rejoin identifiers split by a line break.

    PDF line wrapping cuts DOIs in half, and a DOI reassembled with a space in
    the middle is not the DOI. Applied only to runs that already start with a
    DOI prefix, so ordinary prose is left alone.
    """
    previous = None
    while previous != text:
        previous = text
        text = _WRAPPED.sub(r"\1\2", text)
    return text


def extract_pages(path: str | os.PathLike) -> list[str]:
    """Per-page text. Empty list if the file cannot be read."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "PDF support needs pypdf: pip install -r requirements.txt"
        ) from exc

    logging.getLogger("pypdf").setLevel(logging.CRITICAL)
    try:
        reader = PdfReader(str(Path(path)))
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception:
        # Encrypted, truncated or malformed files cost recall on those files
        # rather than aborting a whole run.
        return []


def split_sections(text: str) -> tuple[str, str]:
    """(main, references) using the last standalone references heading."""
    matches = list(_REF_HEADING.finditer(text))
    if not matches:
        return text, ""
    cut = matches[-1]
    # A heading in the last 5% of the document is a page artefact, not the
    # start of a bibliography that still has content after it.
    if cut.start() > len(text) * 0.97:
        return text, ""
    return text[: cut.start()], text[cut.end():]


def parse_segments(path: str | os.PathLike) -> list[Segment]:
    """Same contract as xmltext.parse_segments."""
    pages = extract_pages(path)
    if not pages:
        return []
    text = _dewrap("\n".join(pages))
    main, references = split_sections(text)
    segments = []
    if main.strip():
        segments.append(Segment(MAIN, _WS.sub(" ", main)))
    if references.strip():
        segments.append(Segment(REFERENCES, _WS.sub(" ", references)))
    return segments
