"""Which DOI prefixes belong to data repositories.

The single largest error source at S2 was DOIs that are perfectly valid and
have nothing to do with data: 221 Crossref Funder Registry entries
(``10.13039``), 123 PLOS article DOIs, 79 IUCr, 51 eLife. Publisher and funder
DOIs outnumbered real data citations three to one.

Filtering on the registrant prefix fixes that. Two sources feed the allowlist,
kept separate because they carry different risks:

**Learned** (``models/doi_prefix_allowlist.txt``) -- prefixes that carry a gold
data citation in the *dev* split. Accurate by construction on dev, but blind to
any repository dev never saw. Two-fold cross-validation inside dev puts that
cost at about 24% of DOI recall on unseen articles.

**A priori** -- well-known data repositories, written down from domain
knowledge rather than read off the labels. These exist to cover exactly the
repositories a learned list would miss, and adding them raised
cross-validated mention F1 from 0.6368 to 0.6511.

Neither list is derived from holdout.

Note what is *absent*: figshare (``10.6084``) and CCDC (``10.5517``). Both are
genuine repositories, and both are near-pure noise in this corpus -- 223 and 75
annotator-rejected candidates against zero real citations. The learned list
excludes them because the labels do, which is the intended behaviour.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

DOI_URL_PREFIX = "https://doi.org/"

_ALLOWLIST_PATH = Path(__file__).resolve().parents[2] / "models" / "doi_prefix_allowlist.txt"

# Well-known data repositories. Domain knowledge, not fitted to any split.
APRIORI_PREFIXES: frozenset[str] = frozenset(
    {
        "10.5061",   # Dryad
        "10.5281",   # Zenodo
        "10.7910",   # Harvard Dataverse
        "10.17605",  # OSF
        "10.1594",   # PANGAEA
        "10.15468",  # GBIF
        "10.5066",   # USGS ScienceBase
        "10.6073",   # EDI / LTER
        "10.17632",  # Mendeley Data
        "10.3886",   # ICPSR
        "10.7937",   # TCIA
        "10.5285",   # NERC Environmental Data Service
        "10.4121",   # 4TU.ResearchData
        "10.17882",  # SEANOE
        "10.25387",
        "10.24381",  # Copernicus Climate Data Store
        "10.18150",
        "10.6075",
        "10.6096",
        "10.5067",   # NASA DAACs
    }
)


def doi_prefix(dataset_id: str) -> str:
    """The registrant prefix of a DOI (``10.5061``), or '' for a non-DOI id."""
    if not dataset_id.startswith(DOI_URL_PREFIX):
        return ""
    rest = dataset_id[len(DOI_URL_PREFIX):]
    head = rest.split("/", 1)[0]
    return head if head.startswith("10.") else ""


@lru_cache(maxsize=1)
def learned_prefixes(path: str | None = None) -> frozenset[str]:
    """Prefixes read from the generated allowlist file, empty if absent."""
    p = Path(path) if path else _ALLOWLIST_PATH
    if not p.exists():
        return frozenset()
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        token = line.split("#", 1)[0].strip()
        if token:
            out.add(token)
    return frozenset(out)


def allowed_prefixes() -> frozenset[str]:
    return learned_prefixes() | APRIORI_PREFIXES


def is_data_doi(dataset_id: str, allowlist: frozenset[str] | None = None) -> bool:
    """True for a DOI from an allowed repository. Non-DOI ids pass through.

    Accession IDs are not filtered here: an accession is already
    repository-specific by construction, so its pattern has done this job.
    """
    prefix = doi_prefix(dataset_id)
    if not prefix:
        return True
    return prefix in (allowlist if allowlist is not None else allowed_prefixes())
