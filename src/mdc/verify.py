"""LLM verification of extracted mentions.

S4 leaves 216 false positives against 432 true ones, and 156 of those false
positives are accession IDs in the main text -- a Pfam or InterPro identifier
named while discussing a protein domain, not cited as data. Telling those apart
needs the sentence, which is what a language model is for.

Applied only to that ambiguous stratum, never to whole articles. Two reasons:
cost, and the fact that the other strata are already at 0.74-0.84 precision
where a fallible verifier is more likely to destroy a true positive than to
catch a false one.

**This only pays off if the verifier is good.** Measured against the S4
baseline on dev, with a verifier of given true-positive-keep and
false-positive-drop rates:

    keep 1.00 / drop 1.00   F1 0.7335  +0.0943   (perfect oracle)
    keep 0.95 / drop 0.80   F1 0.6938  +0.0546
    keep 0.90 / drop 0.70   F1 0.6698  +0.0305
    keep 0.90 / drop 0.50   F1 0.6493  +0.0101
    keep 0.80 / drop 0.50   F1 0.6175  -0.0217
    keep 0.70 / drop 0.70   F1 0.6155  -0.0237

Break-even sits near 85-90% keep with 60-70% drop. Below that the verifier is
worse than not running it, which is why the measured result is reported either
way rather than assumed to be an improvement.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("MDC_LLM_MODEL", "qwen2.5:7b-instruct")

KEEP = "keep"
DROP = "drop"
UNKNOWN = "unknown"

SYSTEM = (
    "You judge whether a scientific article is citing a dataset. "
    "Answer with exactly one word: CITATION or MENTION."
)

TEMPLATE_V1 = """A text fragment from a scientific article is shown below. It contains the identifier:

    {dataset_id}

Decide which of these two the identifier is:

CITATION - the article is pointing at a specific dataset or record as data that
           the authors produced, deposited, analysed, downloaded, or reused.

MENTION  - the identifier appears only in passing: naming a protein family,
           domain, pathway, gene, compound or cell line while discussing
           biology or methods, or listed in a table of annotations, without
           the article citing it as a data source.

Fragment:
\"\"\"
{context}
\"\"\"

One word, CITATION or MENTION:"""


TEMPLATE_V2 = """You are reading one passage from a scientific article.

Identifier: {dataset_id}
Database:   {repository}

Question: in THIS passage, is the article citing {dataset_id} as a data record
it used as data, or just naming it while describing biology or methods?

CITATION - the authors deposited it, downloaded it, analysed it, obtained data
           from it, or point a reader to it to get the data.
MENTION  - it names a protein family, domain, pathway, orthologue, gene,
           compound or cell line as part of an explanation, or sits in a list
           of annotation cross-references.

Examples:
  "sequences were deposited under PRJNA10687"                  -> CITATION
  "raw reads are available from the SRA under SAMN07159041"     -> CITATION
  "proteins carrying the IPR000884 domain were more abundant"   -> MENTION
  "annotated to KEGG orthologue K02388 (flagellar protein)"     -> MENTION

Passage:
\"\"\"
{context}
\"\"\"

Answer with one word, CITATION or MENTION:"""


def repository_of(dataset_id: str) -> str:
    """Name the database an accession belongs to, for the prompt."""
    from mdc.accessions import ALL

    for pattern in ALL:
        if pattern.regex.fullmatch(dataset_id):
            return pattern.repository
    return "unknown"


@dataclass(frozen=True)
class Decision:
    verdict: str
    raw: str

    @property
    def keeps(self) -> bool:
        """Anything other than a confident DROP keeps the mention.

        Fail-open on purpose: an unreachable model, a timeout or an
        unparseable reply must not silently delete recall.
        """
        return self.verdict != DROP


def build_prompt(
    dataset_id: str,
    context: str,
    max_context: int = 1200,
    version: int = 2,
) -> str:
    """Render the verification prompt.

    v1 joined every occurrence of an id into one blob and truncated it, which
    for a frequently-repeated accession produced an unreadable smear of
    unrelated sentences. v2 asks about a single passage, names the database,
    and shows four worked examples.
    """
    if version == 1:
        return TEMPLATE_V1.format(dataset_id=dataset_id, context=context[:max_context])
    return TEMPLATE_V2.format(
        dataset_id=dataset_id,
        repository=repository_of(dataset_id),
        context=context[:max_context],
    )


def cache_key(model: str, prompt: str) -> str:
    return hashlib.sha256(f"{model}\x00{prompt}".encode("utf-8")).hexdigest()[:32]


class Cache:
    """JSON-lines decision cache, so a re-run costs nothing and scores repeat."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.entries: dict[str, str] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.entries[row["key"]] = row["raw"]

    def get(self, key: str) -> str | None:
        return self.entries.get(key)

    def put(self, key: str, raw: str, meta: dict | None = None) -> None:
        self.entries[key] = raw
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "raw": raw, **(meta or {})}) + "\n")


def parse_verdict(raw: str) -> str:
    """Map a reply to keep/drop. Ambiguous or empty replies keep the mention."""
    text = (raw or "").strip().upper()
    if not text:
        return UNKNOWN
    head = text.replace("*", "").replace("`", "").lstrip()
    has_citation = "CITATION" in head
    has_mention = "MENTION" in head
    if has_citation and not has_mention:
        return KEEP
    if has_mention and not has_citation:
        return DROP
    # both present: trust whichever the model said first
    if has_citation and has_mention:
        return KEEP if head.index("CITATION") < head.index("MENTION") else DROP
    return UNKNOWN


def available_models(host: str = DEFAULT_HOST, timeout: float = 5.0) -> list[str]:
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as fh:
            return [m["name"] for m in json.load(fh).get("models", [])]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return []


def ask(
    prompt: str,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_HOST,
    timeout: float = 120.0,
) -> str:
    """One deterministic completion. Returns '' on any failure."""
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "system": SYSTEM,
            "stream": False,
            "options": {"temperature": 0, "seed": 0, "num_predict": 8},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{host}/api/generate", data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as fh:
            return json.load(fh).get("response", "")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"__ERROR__ {type(exc).__name__}"
