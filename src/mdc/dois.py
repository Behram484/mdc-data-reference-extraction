"""Finding and normalising DOIs in free text.

The competition wants every DOI as ``https://doi.org/<prefix>/<suffix>``, so
the scattered forms that occur in real papers -- ``doi:10.x/y``,
``http://dx.doi.org/10.x/y``, a bare ``10.x/y``, an ``https://doi.org/`` link
harvested from an href -- all collapse to one string here.
"""

from __future__ import annotations

import re

DOI_PREFIX = "https://doi.org/"

# A DOI is 10.<registrant>/<suffix>. The suffix runs to whitespace or a
# character that cannot appear in a URL-ish token. Closing brackets are allowed
# through and balanced afterwards, because suffixes genuinely contain them
# (e.g. 10.1016/S0967-0637(01)00025-5).
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)

# Leading noise that precedes a DOI in running text or in a harvested link.
_LEADING = re.compile(
    r"^[\s(\[{<\"'`]*(?:https?://)?(?:(?:dx\.|www\.)?doi\.org/|doi\s*:\s*)*",
    re.IGNORECASE,
)

# Sentence punctuation that is never part of a DOI when it ends the token.
_TRAILING = ".,;:!?'\"`"

_CLOSERS = {")": "(", "]": "[", "}": "{"}


def _trim(doi: str) -> str:
    """Strip sentence punctuation and unbalanced closing brackets from the end.

    A DOI at the end of a sentence picks up the full stop; one inside
    parentheses picks up the closing paren. Neither belongs to the identifier,
    but a bracket that *is* balanced does -- hence counting rather than
    stripping outright.
    """
    while doi:
        last = doi[-1]
        if last in _TRAILING:
            doi = doi[:-1]
            continue
        if last in _CLOSERS and doi.count(last) > doi.count(_CLOSERS[last]):
            doi = doi[:-1]
            continue
        break
    return doi


def normalize_doi(raw: str) -> str | None:
    """Canonicalise one DOI-ish string, or None if it is not a DOI.

    DOIs are case-insensitive by specification and every gold id in
    train_labels.csv is lowercase (verified: 325 of 325), so lowercasing is
    both correct and what the metric expects.
    """
    if not raw:
        return None
    candidate = _trim(_LEADING.sub("", raw.strip()))
    match = DOI_RE.match(candidate)
    if not match:
        return None
    doi = _trim(match.group(0)).lower()
    # a bare "10.1234/" with no suffix is a parse artefact, not an identifier
    if doi.endswith("/"):
        return None
    return DOI_PREFIX + doi


def find_dois(text: str) -> set[str]:
    """Every normalised DOI in a block of text."""
    return {doi for doi, _, _ in find_dois_with_spans(text)}


def find_dois_with_spans(text: str) -> list[tuple[str, int, int]]:
    """Every DOI as (normalised id, start, end) offsets into ``text``.

    The offsets are what makes context extraction possible: the normalised form
    rarely appears verbatim in the document ("doi:10.5061/DRYAD.X" becomes
    "https://doi.org/10.5061/dryad.x"), so a later search for the id would miss
    its own mention.
    """
    out: list[tuple[str, int, int]] = []
    for match in DOI_RE.finditer(text):
        doi = normalize_doi(match.group(0))
        if doi:
            out.append((doi, match.start(), match.end()))
    return out


def article_id_to_doi(article_id: str) -> str:
    """The article's own DOI, recovered from its id.

    article_id is the DOI with '/' replaced by '_'. Only the first underscore
    is the separator -- the prefix is always 10.<digits> -- but 23 of 523 ids
    carry further underscores (10.1051_e3sconf_202017220004), and whether those
    were '_' or '/' in the original is not recoverable. self_doi_key() papers
    over that by treating the two as the same character.
    """
    return article_id.replace("_", "/", 1).lower()


def self_doi_key(doi: str) -> str:
    """Comparison key that ignores the '_' vs '/' ambiguity in article ids.

    Used *only* to decide whether a found DOI is the article's own. Real
    dataset DOIs may contain underscores that must survive, so this collapse
    never touches the emitted prediction.
    """
    stripped = _LEADING.sub("", doi.strip()).lower()
    return stripped.replace("_", "/")


def drop_self_citations(dois: set[str], self_dois: set[str]) -> set[str]:
    """Remove the article's own DOI, which is an id -- not a data citation."""
    blocked = {self_doi_key(d) for d in self_dois}
    return {d for d in dois if self_doi_key(d) not in blocked}
