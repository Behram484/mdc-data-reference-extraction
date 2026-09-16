"""Text extraction from the full-text XML.

The corpus is not one format. Of 400 train files: 331 JATS, 51 GROBID TEI, and
18 in publisher-specific schemas (Elsevier/Springer-style, BioC). A parser
written against any single schema would see a fraction of the data, so nothing
here matches on a document type -- it walks every element, strips namespaces,
and reasons about local tag names only.

Two things this module gets right that a naive ``itertext()`` would not:

1. **Links live in attributes.** Across 60 sample files, DOIs appeared 563
   times in ``ptr@target`` and 323 more in ``href`` attributes. Text-only
   extraction silently loses those.

2. **The reference list has to be separable.** One TEI sample contains 243 DOI
   occurrences against a single gold citation -- the other ~145 are the
   bibliography, i.e. DOIs of cited *papers*, not data. Keeping them would
   destroy precision, so every segment is tagged main/references and the caller
   chooses.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# Local tag names (namespace stripped, lowercased) that open a bibliography,
# across every schema present in the corpus.
REFERENCE_TAGS = frozenset(
    {
        # JATS
        "ref-list", "ref", "element-citation", "mixed-citation",
        "nlm-citation", "citation", "citation-alternatives",
        # TEI / GROBID
        "listbibl", "bibl", "biblstruct", "biblfull", "biblioref",
        # Elsevier / Springer / misc
        "bibliography", "bibliomixed", "reference", "references",
        "citationlist", "bibliographyreference",
    }
)

# Attributes that carry a URL. Namespace-stripped, so xlink:href -> href.
LINK_ATTRS = frozenset({"href", "target", "uri", "url", "link"})

# The article's own DOI in metadata, harvested so it can be excluded rather than
# predicted.
#
# Deliberately narrow. The obvious wider set (TEI <idno type="DOI">, generic
# <doi>) is a trap: in TEI those sit inside every <biblstruct> of the
# bibliography, so harvesting them returned 120 DOIs for one article -- the
# whole reference list, including the gold answer, which would then have been
# excluded. Only tags that mean "this document's own id" qualify, and only
# outside the reference section.
SELF_DOI_TAGS = frozenset({"article-id", "articledoi", "article-doi"})

# Funder DOIs (10.13039/*) are registry entries, never data citations.
SKIP_ATTRS = frozenset({"funderdoi"})

MAIN = "main"
REFERENCES = "references"

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class Segment:
    section: str
    text: str


def _local(tag: object) -> str:
    """Namespace-stripped, lowercased local name. Comments have non-str tags."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _walk(element: ET.Element, in_refs: bool, out: list[Segment]) -> None:
    section = REFERENCES if in_refs else MAIN

    if element.text and element.text.strip():
        out.append(Segment(section, element.text))

    for key, value in element.attrib.items():
        name = _local(key)
        if name in LINK_ATTRS and name not in SKIP_ATTRS and value:
            out.append(Segment(section, value))

    for child in element:
        child_in_refs = in_refs or _local(child.tag) in REFERENCE_TAGS
        _walk(child, child_in_refs, out)
        # a tail belongs to the parent's section, not the child's
        if child.tail and child.tail.strip():
            out.append(Segment(section, child.tail))


def parse_segments(path: str | os.PathLike) -> list[Segment]:
    """Every text and link fragment in the document, tagged main/references.

    Returns an empty list for unparseable XML rather than raising: a handful of
    broken files should cost recall on those files, not abort a whole run.
    """
    try:
        root = ET.parse(Path(path)).getroot()
    except (ET.ParseError, OSError):
        return []
    out: list[Segment] = []
    _walk(root, _local(root.tag) in REFERENCE_TAGS, out)
    return out


def section_text(segments: list[Segment], sections: set[str] | None = None) -> str:
    """Join the requested sections into one whitespace-normalised string.

    Joined with a space, never bare-concatenated: fragments come from separate
    elements, so concatenation would weld the last token of one to the first of
    the next and manufacture ids that are not in the document.
    """
    wanted = sections or {MAIN}
    joined = " ".join(s.text for s in segments if s.section in wanted)
    return _WS.sub(" ", joined).strip()


def self_doi_candidates(path: str | os.PathLike) -> set[str]:
    """DOIs the document declares as its *own* identifier, in any schema."""
    try:
        root = ET.parse(Path(path)).getroot()
    except (ET.ParseError, OSError):
        return set()

    found: set[str] = set()

    def visit(element: ET.Element, in_refs: bool) -> None:
        tag = _local(element.tag)
        if not in_refs and tag in SELF_DOI_TAGS:
            attrs = {_local(k): (v or "").lower() for k, v in element.attrib.items()}
            kind = attrs.get("pub-id-type") or attrs.get("type") or ""
            # an untyped <article-doi> is still the article's doi; a typed id
            # must actually say doi (JATS also carries pmid, pmc, publisher-id)
            if not kind or "doi" in kind:
                if element.text and element.text.strip():
                    found.add(element.text.strip())
        for child in element:
            visit(child, in_refs or _local(child.tag) in REFERENCE_TAGS)

    visit(root, _local(root.tag) in REFERENCE_TAGS)
    return found
