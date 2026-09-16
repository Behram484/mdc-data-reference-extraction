"""S5: ask a local LLM whether an ambiguous mention is really a data citation.

    python scripts/verify_mentions.py --pred outputs/s4_evidence.csv \
        --out outputs/s5_verified.csv --split splits/dev.txt

Only the ambiguous stratum is sent to the model (accession IDs by default, the
source of 156 of S4's 216 false positives). Everything else passes through
untouched. Decisions are cached by (model, prompt) so a re-run is free and the
score reproduces.

--dry-run reports what would be sent without calling the model, and --grade
scores the verifier against the gold labels so its keep/drop rates can be
compared with the break-even table in src/mdc/verify.py.
"""

from __future__ import annotations

import argparse
import os
import time
from collections import Counter
from pathlib import Path

import _paths  # noqa: F401

from mdc.context import collect_evidence
from mdc.data import discover_articles, gold_triples, load_labels
from mdc.evaluate import load_predictions, mentions, write_predictions
from mdc.split import read_split
from mdc.verify import (
    DEFAULT_MODEL,
    DROP,
    KEEP,
    UNKNOWN,
    Cache,
    ask,
    available_models,
    build_prompt,
    cache_key,
    parse_verdict,
)

DOI = "https://doi.org/"


def is_candidate(dataset_id: str, scope: str) -> bool:
    if scope == "accessions":
        return not dataset_id.startswith(DOI)
    if scope == "dois":
        return dataset_id.startswith(DOI)
    return True  # scope == "all"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=os.environ.get("MDC_DATA_DIR", "data"))
    ap.add_argument("--pred", default="outputs/s4_evidence.csv")
    ap.add_argument("--out", default="outputs/s5_verified.csv")
    ap.add_argument("--split", default="splits/dev.txt")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--scope", default="accessions", choices=["accessions", "dois", "all"])
    ap.add_argument("--cache", default="outputs/llm_cache.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="stop after N model calls")
    ap.add_argument("--prompt-version", type=int, default=2, choices=[1, 2])
    ap.add_argument("--sample", type=int, default=0,
                    help="grade on a seeded sample of candidates instead of all")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--grade", action="store_true", help="score the verifier against gold")
    args = ap.parse_args()

    root = Path(args.data_dir)
    split = read_split(args.split)
    pred = {t for t in load_predictions(args.pred) if t[0] in split}
    xml = discover_articles(root / "train" / "XML", "xml")

    labels = load_labels(root / "train_labels.csv")
    gold_mentions = mentions({t for t in gold_triples(labels) if t[0] in split})

    candidates = sorted({(a, d) for a, d, _ in pred if is_candidate(d, args.scope)})
    if args.sample and args.sample < len(candidates):
        import random

        candidates = sorted(random.Random(0).sample(candidates, args.sample))
    print(f"predictions {len(pred)} | candidates ({args.scope}) {len(candidates)}")
    if args.grade:
        true = sum(1 for c in candidates if c in gold_mentions)
        print(f"  of which truly cited: {true}, false: {len(candidates) - true}")

    if args.dry_run:
        print("dry run: no model calls made")
        return 0

    installed = available_models()
    if args.model not in installed:
        print(f"\n!! model {args.model!r} is not installed in Ollama.")
        print(f"   installed: {installed or 'none'}")
        print(f"   pull it with:  ollama pull {args.model}")
        return 2

    # contexts, one article parse each
    contexts: dict[tuple[str, str], str] = {}
    for article_id in sorted({a for a, _ in candidates}):
        path = xml.get(article_id)
        if path is None:
            continue
        for dataset_id, ev in collect_evidence(path, article_id).items():
            # v2 asks about one passage; v1 smeared every occurrence together
            contexts[(article_id, dataset_id)] = (
                ev.contexts[0] if args.prompt_version == 2 else ev.joined_context
            )

    cache = Cache(args.cache)
    verdicts: dict[tuple[str, str], str] = {}
    counts: Counter[str] = Counter()
    calls = 0
    started = time.time()

    for i, (article_id, dataset_id) in enumerate(candidates, 1):
        context = contexts.get((article_id, dataset_id), "")
        if not context:
            verdicts[(article_id, dataset_id)] = UNKNOWN
            counts["no context"] += 1
            continue
        prompt = build_prompt(dataset_id, context, version=args.prompt_version)
        key = cache_key(args.model, prompt)
        raw = cache.get(key)
        if raw is None:
            if args.limit and calls >= args.limit:
                verdicts[(article_id, dataset_id)] = UNKNOWN
                counts["skipped (limit)"] += 1
                continue
            raw = ask(prompt, model=args.model)
            calls += 1
            cache.put(key, raw, {"article_id": article_id, "dataset_id": dataset_id})
            if calls % 25 == 0:
                rate = calls / max(time.time() - started, 1e-9)
                print(f"  {i}/{len(candidates)}  {calls} calls  {rate:.2f}/s")
        verdict = parse_verdict(raw)
        verdicts[(article_id, dataset_id)] = verdict
        counts[verdict] += 1

    kept = {t for t in pred if verdicts.get((t[0], t[1]), UNKNOWN) != DROP}
    write_predictions(args.out, kept)

    print(f"\nmodel {args.model} | {calls} new calls, {len(candidates) - calls} cached")
    for verdict, n in counts.most_common():
        print(f"  {verdict:<18}{n}")
    print(f"dropped {len(pred) - len(kept)} of {len(pred)} predictions -> {args.out}")

    if args.grade:
        true_kept = sum(1 for c in candidates if c in gold_mentions and verdicts.get(c) != DROP)
        true_all = sum(1 for c in candidates if c in gold_mentions)
        false_dropped = sum(
            1 for c in candidates if c not in gold_mentions and verdicts.get(c) == DROP
        )
        false_all = len(candidates) - true_all
        print("\nverifier quality on the candidate stratum:")
        print(f"  keeps true mentions  {true_kept}/{true_all} = "
              f"{true_kept / max(true_all, 1):.1%}")
        print(f"  drops false ones     {false_dropped}/{false_all} = "
              f"{false_dropped / max(false_all, 1):.1%}")
        print("  break-even is roughly 85-90% keep with 60-70% drop "
              "(see src/mdc/verify.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
