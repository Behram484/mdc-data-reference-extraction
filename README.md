# MDC — Data Reference Extraction

Extracting every data citation (DOIs and repository accession IDs) from
scientific full text, and classifying each one as **Primary** (data generated
by this study) or **Secondary** (existing data reused).

Task and data come from the Kaggle competition
[Make Data Count — Finding Data References](https://www.kaggle.com/competitions/make-data-count-finding-data-references)
(data licensed CC0; papers from the Europe PMC open-access subset).

## Independence statement

This is an **independent rebuild, started 2026, written from scratch.**

I competed in this task in 2025 as a team captain and we placed 42nd of 1,282
(silver, private F1 **0.5797** / public 0.7058 — a 0.13 drop, textbook public
leaderboard overfitting). That team's solution was built on a forked public
notebook, so it does not represent work I can point to as my own.

This repository is unrelated to that submission. Nothing is forked from, or
consulted in, any public competition notebook. Third-party models and libraries
are credited in [Credits](#credits). The 0.5797 above is a reference point, not
a target — the goal here is a measured, staged build, not a leaderboard score.

## What this repository is actually for

The deliverable is the table below: **what each technique is worth, measured.**
Every stage is one commit, one number, and an honest note when a stage does not
help.

| Stage | Technique | Precision | Recall | F1 | Δ F1 | Mention F1 |
|-------|-----------|-----------|--------|-----|------|------------|
| S0 | Empty baseline (pipeline check) | 0.0000 | 0.0000 | 0.0000 | — | 0.0000 |
| S1 | XML parsing + DOI regex | 0.1201 | 0.1802 | **0.1442** | +0.1442 | 0.1583 |
| S2 | + accession ID patterns | 0.2752 | 0.6131 | **0.3799** | +0.2357 | 0.4050 |
| S3 | + repository prefix filter, reference mining | 0.5741 | 0.6572 | **0.6129** | +0.2330 | 0.7117 |
| S4 | + Primary/Secondary rules | 0.5988 | 0.6855 | **0.6392** | +0.0263 | 0.7117 |
| S5 | + LLM verification of ambiguous mentions | 0.5894 | 0.5477 | 0.5678 | **−0.0714** | 0.6465 |
| S6 | + PDF fallback | _pending_ | | | | |

**S5 made things worse and is not in the shipped pipeline.** The best
configuration remains S4 at F1 0.6392. The row is kept because a measured
negative result is the point of this table.

**Mention F1** scores `(article_id, dataset_id)` with the type dropped. S1–S3
are purely about *finding* citations and emit a constant type, so their headline
F1 is capped by how often that constant happens to be right. Mention F1 is the
honest measure of extraction until S4 adds a real classifier.

Scores are measured on the local `dev` split (418 articles, 566 gold triples),
not the Kaggle leaderboard. `holdout` (105 articles, 153 triples) stays sealed
until the end. S2 is broken down per repository pattern so the contribution of
each one is visible.

The public `test/` directory holds only 25 XML / 30 PDF files — it is a format
sample, not the real test set, which is served at rerun time. Local evaluation
is therefore the only usable feedback loop.

## What is in the data

Measured with `scripts/inspect_data.py`, not assumed:

| | |
|---|---|
| train articles | 523 labelled (400 XML, 524 PDF — 76.3% have XML) |
| label rows | 1066 → **719 real citations** + 347 rejected |
| articles carrying a citation | 214 of 523 |
| citations per citing article | 3.36 mean, 32 max |
| type mix | Secondary 449, Primary 270 |

Three findings that shape the plan:

**`Missing` is a type, not a sentinel.** It appears 347 times in the `type`
column and never in `dataset_id`. It marks a candidate id that annotators found
in the text and then *rejected*. No article mixes `Missing` with real labels, so
the 309 articles carrying only `Missing` rows are the true negatives — anything
predicted for them is a false positive.

Those 347 rejected ids are the single most useful thing in the training data for
precision: they are exactly the shapes that look like data citations but are
not. Grouped by DOI prefix, the split is near-total —

| DOI prefix | Missing | Primary | Secondary |
|---|---|---|---|
| `10.6084` figshare | 223 | 0 | 0 |
| `10.5517` CCDC | 75 | 0 | 0 |
| `10.17182` | 23 | 0 | 0 |
| `10.5061` Dryad | 3 | 79 | 0 |
| `10.5281` Zenodo | 0 | 21 | 1 |
| `10.5066` USGS | 0 | 10 | 26 |

— so figshare and CCDC DOIs are pure noise here (321 of 347 rejections), while
Dryad is almost always Primary. S2 and S3 act on this rather than guessing.

**Secondary outnumbers Primary, 449 to 270.** Worth stating because the
opposite is the intuitive assumption, and a "predict everything Primary"
fallback in S4 would be a *worse* baseline than it first looks.

**Recall is capped at 89.7% without PDFs.** 645 of the 719 gold triples sit in
articles that have XML; the other 74 are reachable only through S6's PDF
fallback. Every recall figure for S1–S5 should be read against that ceiling.


## S1 — XML parsing and DOI extraction

Regex `10.\d{4,9}/...` over the full text, normalised to
`https://doi.org/<lowercase doi>`, with the article's own DOI removed.

Two structural decisions dominate the result, and both were measured rather
than assumed:

| Configuration | Precision | Recall | F1 |
|---|---|---|---|
| main text only | 0.1201 | 0.1802 | **0.1442** |
| including the reference list | 0.0100 | 0.2244 | 0.0192 |
| main text, own DOI not excluded | 0.0848 | 0.1802 | 0.1153 |

**Excluding the bibliography is worth 7.5× F1.** A reference list is a dense
block of DOIs of cited *papers* — one sample article has 243 DOI occurrences
against a single gold citation. Reading it adds 47 true mentions and 11,775
false ones.

**Excluding the article's own DOI is worth +0.029 F1** — it removes 354 false
positives, since a paper's own identifier appears throughout its own metadata.

### Where the remaining recall goes

Of the 252 gold DOI citations in `dev` (the only ones S1 can address — the
other 314 are accession IDs, which is S2):

| | count | share |
|---|---|---|
| found in main text | 112 | 44.4% |
| **only in the reference list** | 62 | 24.6% |
| article has no XML | 59 | 23.4% |
| not present in the XML at all | 18 | 7.1% |
| present but missed by the regex | 1 | 0.4% |

The regex itself is not the bottleneck — it misses one citation out of 252.

The 62 in the reference list are the interesting number: they are real data
citations formatted as bibliography entries. Reading the whole bibliography to
reach them costs 11,775 false positives, but reading *only* entries whose DOI
prefix belongs to a known data repository should recover most of them for
almost nothing. That is an S3 experiment, backed by this measurement rather
than by a guess.

### Type constant

S1 labels everything **Primary**. Among gold DOI citations the split is 215
Primary / 110 Secondary, so Primary is the majority for *this* subset — the
reverse of the corpus as a whole (449 Secondary / 270 Primary), a skew that
turns out to come entirely from accession IDs:

| | Primary | Secondary |
|---|---|---|
| DOI citations | 215 | 110 |
| accession IDs | 55 | 339 |

Format alone therefore predicts type at about 77% accuracy, which is the
baseline S4 has to beat.


## S2 — Accession ID patterns

Twelve repository patterns, each one derived from the gold labels rather than
from a general list of bioinformatics databases. That distinction turned out to
matter: the obvious candidates barely occur in this corpus, while the
repositories that carry most of the data appear on no such list.

| Pattern from the usual list | gold citations here |
|---|---|
| GEO `GSE`/`GSM` | 3 / 0 |
| SRA `SRR` | 4 |
| ENA `ERR` / `PRJEB` | 1 / 0 |
| dbGaP `phs` | 0 |

| What actually carries the data | gold citations |
|---|---|
| BioSample `SAMN\d{5,}` | 41 |
| ArrayExpress `E-[A-Z]{4}-\d+` | 37 |
| GISAID `EPI_ISL_\d+` / `EPI\d{6,}` | 35 / 29 |
| InterPro `IPR\d{6}` | 33 |
| ChEMBL `CHEMBL\d+` | 29 |
| BioProject `PRJNA\d+` | 26 |
| Pfam `PF\d{5}` | 21 |
| Ensembl `ENS[A-Z]*[GTP]\d{11}` | 21 |
| KEGG orthologs `K\d{5}` | 20 |
| Cellosaurus `CVCL_\w{4}` | 14 |
| PRIDE `PXD\d{6}` | 10 |

### Which patterns earn their place

`scripts/eval_patterns.py --cumulative` adds patterns to the S1 baseline one at
a time, best measured precision first. Mention-level F1 on dev:

| + pattern | precision | recall | F1 | Δ F1 |
|---|---|---|---|---|
| (S1, DOI only) | 0.132 | 0.198 | 0.1583 | |
| + gisaid_epi | 0.160 | 0.247 | 0.1940 | +0.0357 |
| + chembl | 0.185 | 0.295 | 0.2272 | +0.0332 |
| + interpro | 0.208 | 0.341 | 0.2580 | +0.0308 |
| + gisaid_isl | 0.226 | 0.380 | 0.2833 | +0.0252 |
| + arrayexpress | 0.253 | 0.445 | 0.3225 | +0.0392 |
| + pfam | 0.267 | 0.482 | 0.3436 | +0.0212 |
| + cellosaurus | 0.277 | 0.511 | 0.3592 | +0.0156 |
| + pride | 0.282 | 0.528 | 0.3678 | +0.0085 |
| + bioproject | 0.291 | 0.572 | 0.3855 | +0.0177 |
| + kegg_ortholog | 0.297 | 0.608 | 0.3986 | +0.0131 |
| + biosample | 0.295 | 0.638 | 0.4038 | +0.0052 |
| **+ ensembl** | 0.293 | **0.654** | **0.4050** | +0.0012 |
| + sra_run | 0.288 | 0.663 | 0.4019 | −0.0031 |
| + cath | 0.275 | 0.687 | 0.3929 | −0.0090 |
| + genbank | 0.209 | 0.696 | 0.3218 | **−0.0698** |
| + pdb | 0.201 | 0.703 | 0.3120 | −0.0097 |
| + geo | 0.193 | 0.708 | 0.3036 | −0.0085 |
| + refseq · dbsnp · uniprot | | | 0.2937 | −0.0099 |

Everything after `ensembl` makes the score worse, so the selected set stops
there. Four patterns are individually destructive:

| Pattern | tp | fp | precision | why |
|---|---|---|---|---|
| `genbank` `[A-Z]{1,2}\d{5,6}` | 42 | 483 | 0.080 | collides with gene names and figure labels |
| `cath` `\d.\d.\d.\d` | 14 | 100 | 0.123 | identical in shape to a version number |
| `pdb` 4-char code | 4 | 98 | 0.039 | matches ordinary words — `5min`, `2x4b` |
| `geo` `GSE\d+` | 3 | 88 | 0.033 | almost no gold support here to begin with |

The handoff plan predicted PDB would be the precision disaster. It is — 0.039
precision — but `genbank` is worse in absolute terms, costing 483 false
positives against 42 true ones, and it was not on the list of suspects at all.

Two patterns are *excluded despite having gold support*: `empiar` (12) and
`hpa` (9). Every one of their gold citations landed in holdout, so dev gives no
evidence either way. They would probably help — but selecting them on the
strength of holdout labels is precisely the contamination that would make the
final holdout number meaningless. They stay in the registry, out of the
selection.

### Type assignment

S2 replaces S1's constant with the **format prior**: DOI → Primary, accession →
Secondary. This is not a classifier, it is the measured base rate, and it is
worth more than any constant:

| Type rule | Precision | Recall | F1 |
|---|---|---|---|
| constant Primary | 0.0912 | 0.2032 | 0.1259 |
| constant Secondary | 0.2022 | 0.4505 | 0.2791 |
| **format prior** | 0.2752 | 0.6131 | **0.3799** |

Type errors are now a rounding error in the total: of 914 false positives, only
23 are a mention found with the wrong type. The other 891 are spurious mentions.
**Precision, not classification, is what S3 has to fix.**


## S3 — Cutting false positives

S2 left 891 false mentions against 370 true ones. Their composition decided
what to build:

| | count | share |
|---|---|---|
| DOIs | 737 | 83% |
| accession IDs | 154 | 17% |

and the DOIs were overwhelmingly *valid DOIs that are not data*:

| prefix | false positives | gold | what it is |
|---|---|---|---|
| `10.13039` | 221 | 0 | Crossref Funder Registry |
| `10.1371` | 123 | 0 | PLOS |
| `10.1107` | 79 | 0 | IUCr |
| `10.7554` | 51 | 0 | eLife |
| `10.1111` · `10.1002` | 87 | 0 | Wiley |

Publisher and funder DOIs outnumbered real data citations three to one.

### Normalisation and dedup contributed nothing — and that is the finding

The stage was planned as "normalise, dedup, cut false positives". The first two
turned out to be already done: dedup is structural (predictions are a set of
triples, so a repeated mention cannot double-count) and DOI normalisation
landed in S1. Auditing every false positive that was a near-variant of a gold
id in the same article returned 47 candidates, and all 47 were genuinely
*different* identifiers — `K02406` against gold `K02407`, `10.17882/47142`
against gold `10.17882/49388`. There was no normalisation bug left to fix, so
S3's gain comes entirely from prefix filtering and reference mining.

### Choosing the filter honestly

Allowlisting the DOI prefixes seen in dev gold removes 706 of 737 false DOIs
while keeping all 252 true ones — but that number is fitted to dev and would
flatter a repository list that has simply memorised the split. To estimate what
it is worth on *unseen* articles, the rule is refit inside dev: build the list
on one half, score on the other, 2 folds × 5 seeds.

| Rule | Precision | Recall | Mention F1 |
|---|---|---|---|
| no filter (S2) | 0.2934 | 0.6537 | 0.4050 |
| blocklist publisher prefixes | 0.5282 | 0.6527 | 0.5838 |
| hybrid allow-or-not-blocked | 0.5282 | 0.6527 | 0.5838 |
| **allowlist data repositories** | 0.6600 | 0.6152 | **0.6368** |
| allowlist + a-priori repositories | 0.6641 | 0.6385 | **0.6511** |

An unseen repository prefix costs about 24% of DOI recall — the honest price of
the allowlist, and still far cheaper than the precision it buys. Adding
twenty well-known data-repository prefixes from domain knowledge (not from the
labels) recovers part of that, worth +0.014 cross-validated.

The learned half lives in
[`models/doi_prefix_allowlist.txt`](models/doi_prefix_allowlist.txt), generated
from **dev only** by `scripts/build_allowlist.py` and committed so the scores
reproduce. figshare (`10.6084`) and CCDC (`10.5517`) are absent even though both
are real repositories: in this corpus they contribute 223 and 75
annotator-rejected candidates and zero real citations, and the learned list
excludes them because the labels do.

### Reference mining, now that it is safe

S1 measured 62 gold DOIs that appear *only* in the bibliography, and found that
reading the whole reference list costs 11,775 false positives to recover 47 of
them. With the prefix filter in place the same read becomes cheap:

| Reading the bibliography | true mentions gained | false positives |
|---|---|---|
| unfiltered (S1) | 47 | 11,775 |
| allowed prefixes only (S3) | **62** | **29** |

### The cost, stated plainly

| Configuration | F1 | Mention F1 |
|---|---|---|
| S2 | 0.3799 | 0.4050 |
| S3, allowlist only | 0.6191 | 0.6601 |
| **S3, allowlist + reference mining** | **0.6129** | **0.7117** |

Reference mining raises extraction sharply (+0.053 mention F1) while *lowering*
the headline F1 by 0.005. That is not a contradiction — it is a typing failure.
The format prior calls every DOI Primary, but a data citation formatted as a
bibliography entry is usually someone else's data:

| Where the DOI was found | Primary | Secondary | majority |
|---|---|---|---|
| main text only | 49 | 7 | Primary (88%) |
| main text and bibliography | 53 | 3 | Primary (95%) |
| **bibliography only** | 25 | 37 | **Secondary (60%)** |

S3 keeps reference mining because finding the citation is S3's job and the
extraction gain is real. Fixing the label is S4's, and location is now a
measured signal rather than a guess. The shift is already visible in the error
mix: wrong-type errors were 23 of 914 false positives at S2, and are 60 of 274
now.


## S4 — Primary vs Secondary

S3 left type errors as 60 of 274 false positives. This stage classifies, and
the mention-level F1 is unchanged by design (0.7117 before and after) — S4
moves labels, not extraction.

Accuracy is measured on the 432 correctly-extracted dev mentions, so it
reflects the classifier alone rather than the extractor's mistakes:

| Rule | Accuracy |
|---|---|
| always Secondary (majority class) | 67.6% |
| format prior — DOI→Primary, accession→Secondary (S2/S3) | 86.1% |
| format + location | 88.9% |
| **+ learned repository prefix** | **89.4%** |

### Where the signal actually is

Two features do all the work, and a cross-tab shows why — only one cell of four
is genuinely uncertain:

| Location | Format | Primary | Secondary | majority |
|---|---|---|---|---|
| main + bibliography | DOI | 53 | 3 | Primary (95%) |
| main only | DOI | 49 | 7 | Primary (88%) |
| main only | accession | 13 | 245 | Secondary (95%) |
| **bibliography only** | **DOI** | **25** | **37** | **Secondary (60%)** |

A repository's own habits then override where they are known: Dryad is 65–0
Primary in dev, ICPSR 0–18 Secondary, GBIF 10–24 Secondary. Eleven prefixes
clear the ≥5-citation support threshold; they live in
[`models/doi_prefix_types.txt`](models/doi_prefix_types.txt), learned from dev.

### Context keywords do not work here

This stage was planned around a keyword lexicon. Measured against dev contexts,
most of it simply is not in the text, and two of the phrases point the wrong
way:

| Phrase | expected | hits | actual Primary rate |
|---|---|---|---|
| "data generated for this study" | Primary | **0** | — |
| "we deposited" | Primary | **0** | — |
| "were generated" | Primary | **0** | — |
| "previously published" | Secondary | **0** | — |
| "reused" | Secondary | **0** | — |
| "obtained from" | Secondary | 1 | — |
| "downloaded from" | Secondary | 6 | 50% (no signal) |
| "publicly available" | Secondary | 7 | **86% Primary** |
| "available from" | Secondary | 37 | **70% Primary** |

The best cue-based variant was worth +0.15pp against a seed-to-seed standard
deviation of 0.5–0.7pp — noise — and most variants made the rule worse. No
keyword rule ships.

### A trap worth naming

Mining n-grams for discriminative power initially produced beautiful-looking
predictors: `duck egypt`, `flagellar`, `cell lines`, all at 0% Primary with
n≈26. They are not language, they are **article identity**. One paper
contributes dozens of mentions sharing the same surrounding text, so ungrouped
folds let a rule recognise the article and score far above what it would earn
on a new one.

Every number in this section therefore comes from **article-grouped** 5-fold
cross-validation inside dev, repeated across seeds. It is the same reason the
dev/holdout split is by article (S0) — the mistake simply reappears one level
down.


## S5 — LLM verification (negative result)

S4's errors are 216 false positives against 432 true ones, and 156 of those
false positives are accession IDs in the main text: a Pfam or InterPro
identifier named while discussing a protein domain rather than cited as data.
Telling those apart needs the sentence, so this stage asks a local model
(Ollama, `qwen2.5:7b-instruct`, 414 calls, temperature 0) to judge each one.

**It does not work, and the pipeline does not use it.**

### The break-even was computed first

Before spending anything, the sensitivity of F1 to verifier quality was
measured by simulating verifiers of known accuracy against dev:

| keeps true mentions | drops false ones | F1 | Δ vs S4 |
|---|---|---|---|
| 1.00 | 1.00 | 0.7335 | +0.0943 (perfect oracle) |
| 0.95 | 0.80 | 0.6938 | +0.0546 |
| 0.90 | 0.70 | 0.6698 | +0.0305 |
| 0.90 | 0.50 | 0.6493 | +0.0101 |
| 0.80 | 0.50 | 0.6175 | −0.0217 |
| 0.70 | 0.70 | 0.6155 | −0.0237 |

Break-even needs roughly 85–90% keep with 60–70% drop. Below that a verifier
destroys more true mentions than it removes false ones.

### What the model actually did

| Verifier | keeps true | drops false | overall accuracy |
|---|---|---|---|
| **do nothing (keep everything)** | 100% | 0% | **66.7%** |
| prompt v1 — joined contexts | 69.0% | 26.0% | 54.7% |
| prompt v2 — single passage, database named, 4 examples | 41.0% | 42.0% | 41.3% |

Both prompts score **worse than not running the model at all**. On the full
414 candidates, v1 keeps 69.4% of true mentions and drops 27.6% of false ones,
which lands in the loss region of the table above and costs 0.0714 F1 —
sacrificing 79 correct citations to remove 43 wrong ones.

The second prompt was one deliberate iteration, not open-ended fiddling: the
first version smeared every occurrence of an identifier into one truncated
blob, which is a real implementation flaw worth fixing before blaming the
model. Naming the database and giving four worked examples made the model far
more willing to answer MENTION — better at dropping, much worse at keeping,
and worse overall.

### Honest limits of this result

This says a 7B model with these two prompts fails the task. It does not show
that no LLM can do it. A larger model was not tried: the machine has 6 GB of
VRAM, so anything past ~7B spills to CPU, and 414 calls already took 18 minutes
at 0.39 calls/s with the model fully resident on the GPU. The 414 decisions are
archived in [`reports/llm_decisions.jsonl`](reports/llm_decisions.jsonl) so the
claim can be checked rather than taken on trust.

The infrastructure stays in the repository and is a one-flag run against any
Ollama model, so the experiment is cheap to repeat when better hardware or a
better prompt is available:

```bash
python scripts/verify_mentions.py --model <model> --prompt-version 2 --sample 150 --grade
```

Verification fails **open** by design: an unreachable model, a timeout or an
unparseable reply keeps the mention. A verifier outage costs precision, never
recall.

## Evaluation

Micro-averaged F1 over exact `(article_id, dataset_id, type)` triples, matching
the competition metric:

- The same `(dataset_id, type)` inside one article counts once — the scorer uses
  sets, so this is structural rather than a cleanup step.
- An article with no data citation must not appear in the predictions. If it
  does, every predicted row for it is a false positive.
- DOIs must be normalised to `https://doi.org/<prefix>/<suffix>`.

The scorer ([`src/mdc/evaluate.py`](src/mdc/evaluate.py)) does **exact string
matching and nothing else**. All normalisation lives in the prediction pipeline
on purpose: a scorer that quietly canonicalises both sides would hide the very
bugs S3 exists to find.

Beyond the headline number it reports per-type scores and splits false
positives into *spurious mention* (not a citation at all) versus *wrong type*
(mention found, Primary/Secondary call wrong) — two failures with completely
different fixes.

### Splits

`dev` / `holdout` are **split by `article_id`, never by row**. Two citations in
the same paper share the same full text, so a row-level split would let the
pipeline see the answer for a paper it is then scored on. Default 80/20,
`seed=42`. The id lists live in `splits/` and are committed, so every number in
the table above is reproducible.

The split covers *all* labelled articles, including those with no citation —
those true negatives are what keeps precision meaningful. It is **stratified on
whether an article cites anything**: only 214 of 523 do, and an unstratified
draw at seed 42 left dev at 42.1% citing against holdout's 36.2%, which would
shift the achievable precision between the two halves. Stratified, both sit at
40.9% / 41.0%.

Every scored run is appended to [`reports/scores.jsonl`](reports/scores.jsonl)
via `--json-out`.

## Layout

```
src/mdc/data.py       load train_labels.csv, discover article files
src/mdc/xmltext.py    schema-agnostic XML text, split main vs references
src/mdc/dois.py       DOI regex, normalisation, self-citation removal
src/mdc/accessions.py repository accession patterns + the selected set
src/mdc/repositories.py DOI prefix allowlist: which registrants are data
src/mdc/context.py    per-mention evidence: location + surrounding text
src/mdc/classify.py   the Primary/Secondary rule
src/mdc/verify.py     LLM verification client, prompts, decision cache
src/mdc/pipeline.py   article -> predicted ids, shared by every stage
src/mdc/evaluate.py   precision / recall / F1, error breakdowns, I/O
src/mdc/split.py      article-level dev / holdout split
scripts/inspect_data.py   report what is on disk before trusting it
scripts/make_split.py     write splits/dev.txt and splits/holdout.txt
scripts/predict_empty.py  the null baseline
scripts/predict.py        rule-based prediction; stages are its configurations
scripts/eval_patterns.py  per-pattern cost/benefit and the cumulative sweep
scripts/build_allowlist.py learn the DOI prefix allowlist from dev
scripts/build_prefix_types.py learn the majority type per repository
scripts/verify_mentions.py S5: LLM verification of ambiguous mentions
models/                   learned parameters, committed for reproducibility
scripts/score.py          score a prediction CSV against a split
tests/test_pipeline.py    end-to-end check on a synthetic fixture
tests/test_extraction.py  DOI normalisation and XML parsing units
tests/test_accessions.py  accession patterns and the format prior
tests/test_repositories.py the DOI prefix allowlist
tests/test_classify.py    evidence collection and the type rule
tests/test_verify.py      reply parsing, caching, fail-open policy
splits/                   committed dev / holdout article-id lists
reports/scores.jsonl      one line per scored run
```

Python 3.12, standard library only so far. No dependencies are added until a
stage actually needs one.

## Data setup

The data (~2 GB, 981 files) is not in this repository and `data/` is gitignored.
Download it from the competition page and unzip so that:

```
data/
  train/XML/<article_id>.xml
  train/PDF/<article_id>.pdf
  test/XML/   test/PDF/
  train_labels.csv        article_id, dataset_id, type
  sample_submission.csv   row_id, article_id, dataset_id, type
```

`--data-dir` accepts any path, so the data can live outside the repo. Set
`MDC_DATA_DIR` once and every script picks it up:

```bash
export MDC_DATA_DIR=/path/to/mdc-data     # PowerShell: $env:MDC_DATA_DIR="D:\kaggle"
python scripts/inspect_data.py
```

## Running

```bash
python scripts/inspect_data.py
python scripts/make_split.py
python scripts/predict.py --split splits/dev.txt --out outputs/s2.csv --patterns selected
python scripts/score.py --pred outputs/s2.csv --split splits/dev.txt --label "S2"
python scripts/eval_patterns.py --split splits/dev.txt --cumulative
python -m unittest discover -s tests -v
```

`scripts/score.py` prints a ready-to-paste markdown row for the table above,
and `--json-out` appends the run to a JSON-lines log.

## Credits

- Competition data: Make Data Count / Kaggle, CC0.
- Papers: Europe PMC open-access subset.
- Third-party models and libraries will be listed here as stages introduce them.
