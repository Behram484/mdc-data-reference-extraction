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

| Stage | Technique | Precision | Recall | F1 | Δ F1 |
|-------|-----------|-----------|--------|-----|------|
| S0 | Empty baseline (pipeline check) | 0.0000 | 0.0000 | 0.0000 | — |
| S1 | XML parsing + DOI regex | _pending_ | | | |
| S2 | + accession ID patterns | _pending_ | | | |
| S3 | + normalisation and dedup | _pending_ | | | |
| S4 | + Primary/Secondary rules | _pending_ | | | |
| S5 | + LLM on ambiguous cases only | _pending_ | | | |
| S6 | + PDF fallback | _pending_ | | | |

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
src/mdc/evaluate.py   precision / recall / F1, error breakdowns, I/O
src/mdc/split.py      article-level dev / holdout split
scripts/inspect_data.py   report what is on disk before trusting it
scripts/make_split.py     write splits/dev.txt and splits/holdout.txt
scripts/predict_empty.py  the null baseline
scripts/score.py          score a prediction CSV against a split
tests/test_pipeline.py    end-to-end check on a synthetic fixture
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
python scripts/predict_empty.py --out outputs/s0_empty.csv
python scripts/score.py --pred outputs/s0_empty.csv --split splits/dev.txt --label "S0 empty baseline"
python -m unittest discover -s tests -v
```

`scripts/score.py` prints a ready-to-paste markdown row for the table above,
and `--json-out` appends the run to a JSON-lines log.

## Credits

- Competition data: Make Data Count / Kaggle, CC0.
- Papers: Europe PMC open-access subset.
- Third-party models and libraries will be listed here as stages introduce them.
