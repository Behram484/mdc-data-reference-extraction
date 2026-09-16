"""Repository accession-ID patterns.

Every pattern here was derived from the gold labels, not from a generic list of
"common bioinformatics databases". That distinction matters: the obvious
candidates (GEO GSE/GSM, SRA SRR, ENA PRJEB, dbGaP phs) barely occur in this
corpus -- 3, 0, 4, 0 and 0 gold citations respectively -- while the ones that
actually carry the data (InterPro 33, BioSample 41, GISAID 64, ChEMBL 29,
Pfam 21, KEGG 20) appear on no such list.

``gold`` on each pattern records how many gold citations it is responsible for,
so a pattern that stops earning its keep is visible rather than inherited.

Accession IDs are emitted **exactly as written in the text**. Unlike DOIs they
are not case-insensitive: the gold set contains both ``5VA1`` and ``2nrj``, so
normalising case would break as many matches as it fixed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Pattern:
    name: str
    repository: str
    regex: re.Pattern[str]
    gold: int = 0
    note: str = ""


def _p(name: str, repository: str, pattern: str, gold: int = 0, note: str = "") -> Pattern:
    # \b alone is wrong here: it would fire inside longer alphanumeric tokens
    # (a version string, a hash). Guard with explicit non-token neighbours.
    return Pattern(
        name=name,
        repository=repository,
        regex=re.compile(rf"(?<![A-Za-z0-9_\-./]){pattern}(?![A-Za-z0-9_\-])"),
        gold=gold,
        note=note,
    )


# --- patterns with solid gold support -------------------------------------
CORE: tuple[Pattern, ...] = (
    _p("biosample", "NCBI BioSample", r"SAM[NED][A-Z]?\d{5,}", gold=41),
    _p("gisaid_isl", "GISAID", r"EPI_ISL_\d{3,}", gold=35),
    _p("interpro", "InterPro", r"IPR\d{6}", gold=33),
    _p("chembl", "ChEMBL", r"CHEMBL\d{3,}", gold=29),
    _p("gisaid_epi", "GISAID", r"EPI\d{6,}", gold=29),
    _p("bioproject", "NCBI BioProject", r"PRJ[NED][A-Z]\d{3,}", gold=26),
    _p("arrayexpress", "ArrayExpress/BioStudies", r"E-[A-Z]{4}-\d+", gold=37),
    _p("pfam", "Pfam", r"PF\d{5}", gold=21),
    _p("kegg_ortholog", "KEGG", r"K\d{5}", gold=20),
    _p("ensembl", "Ensembl", r"ENS[A-Z]{0,6}[GTP]\d{11}", gold=21),
    _p("cellosaurus", "Cellosaurus", r"CVCL_[A-Z0-9]{4}", gold=14),
    _p("empiar", "EMPIAR", r"EMPIAR-\d{4,}", gold=12),
    _p("pride", "PRIDE", r"PXD\d{6}", gold=10),
    _p("hpa", "Human Protein Atlas", r"HPA\d{6}", gold=9),
    # UniProt's own published accession grammar
    _p(
        "uniprot",
        "UniProt",
        r"(?:[OPQ]\d[A-Z0-9]{3}\d|[A-NR-Z]\d(?:[A-Z][A-Z0-9]{2}\d){1,2})",
        gold=34,
    ),
)

# --- low-support or structurally risky ------------------------------------
# Kept separate so their cost can be measured before they are trusted.
RISKY: tuple[Pattern, ...] = (
    _p("geo", "NCBI GEO", r"GS[EM]\d{3,}", gold=3),
    _p("sra_run", "NCBI SRA", r"[SED]RR\d{5,}", gold=4),
    _p("sra_study", "NCBI SRA", r"[SED]RP\d{5,}", gold=1),
    _p("refseq", "RefSeq", r"N[MCGRPTWZ]_\d{6,}(?:\.\d+)?", gold=2),
    _p("dbsnp", "dbSNP", r"rs\d{4,}", gold=1),
    _p(
        "genbank",
        "GenBank/ENA",
        r"[A-Z]{1,2}\d{5,6}(?:\.\d+)?",
        gold=8,
        note="two letters plus digits collides with figure labels and gene names",
    ),
    _p(
        "cath",
        "CATH",
        r"\d\.\d{1,3}\.\d{1,4}\.\d{1,4}",
        gold=14,
        note="indistinguishable from version numbers and numbered section headings",
    ),
    _p(
        "pdb",
        "PDB",
        r"\d[A-Za-z][A-Za-z0-9]{2}",
        gold=4,
        note="any digit + 3 alphanumerics; matches ordinary words and measurements",
    ),
)

ALL: tuple[Pattern, ...] = CORE + RISKY

# The set that survives measurement on dev, in the order the cumulative sweep
# added them (best measured precision first). Everything after `ensembl` made
# the score worse -- see the S2 table in the README.
#
# `empiar` and `hpa` are absent for a reason worth stating: their gold
# citations all landed in holdout, so dev gives zero evidence either way. They
# would very likely help, but adding them on the strength of holdout labels is
# exactly the contamination that makes a final holdout number meaningless.
# They stay in the registry, out of the selection.
SELECTED_NAMES: tuple[str, ...] = (
    "gisaid_epi", "chembl", "interpro", "gisaid_isl", "arrayexpress",
    "pfam", "cellosaurus", "pride", "bioproject", "kegg_ortholog",
    "biosample", "ensembl",
)

BY_NAME: dict[str, Pattern] = {p.name: p for p in ALL}

SELECTED: tuple[Pattern, ...] = tuple(BY_NAME[n] for n in SELECTED_NAMES)


def find_accessions(text: str, patterns: tuple[Pattern, ...] = SELECTED) -> set[str]:
    """Every accession ID in the text, as written."""
    out: set[str] = set()
    for pattern in patterns:
        out.update(pattern.regex.findall(text))
    return out


def find_accessions_with_spans(
    text: str, patterns: tuple[Pattern, ...] = SELECTED
) -> list[tuple[str, int, int]]:
    """Every accession as (id, start, end) offsets into ``text``."""
    out: list[tuple[str, int, int]] = []
    for pattern in patterns:
        for match in pattern.regex.finditer(text):
            out.append((match.group(0), match.start(), match.end()))
    return out


def find_by_pattern(
    text: str, patterns: tuple[Pattern, ...] = ALL
) -> dict[str, set[str]]:
    """Same, but attributed to the pattern that produced each id."""
    return {p.name: set(p.regex.findall(text)) for p in patterns}


def resolve(names: str) -> tuple[Pattern, ...]:
    """Turn a comma-separated selection into patterns. 'core', 'risky', 'all'."""
    if names in ("selected", ""):
        return SELECTED
    if names == "core":
        return CORE
    if names == "risky":
        return RISKY
    if names == "all":
        return ALL
    if names == "none":
        return ()
    chosen = []
    for name in (n.strip() for n in names.split(",") if n.strip()):
        if name not in BY_NAME:
            raise KeyError(f"unknown pattern {name!r}; have {sorted(BY_NAME)}")
        chosen.append(BY_NAME[name])
    return tuple(chosen)
