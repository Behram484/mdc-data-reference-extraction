"""Unit tests for the LLM verification layer.

No model is contacted: these cover reply parsing, caching and the fail-open
policy, which are the parts that decide whether a model outage quietly deletes
predictions.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mdc.verify import (  # noqa: E402
    DROP,
    KEEP,
    UNKNOWN,
    Cache,
    Decision,
    build_prompt,
    cache_key,
    parse_verdict,
)


class TestParseVerdict(unittest.TestCase):
    def test_clean_answers(self):
        self.assertEqual(parse_verdict("CITATION"), KEEP)
        self.assertEqual(parse_verdict("MENTION"), DROP)

    def test_tolerates_formatting_and_case(self):
        for raw, expected in (
            ("  citation.", KEEP),
            ("**MENTION**", DROP),
            ("`Citation`", KEEP),
            ("Answer: MENTION\n", DROP),
        ):
            self.assertEqual(parse_verdict(raw), expected, raw)

    def test_both_words_resolves_to_whichever_came_first(self):
        self.assertEqual(parse_verdict("MENTION, not CITATION"), DROP)
        self.assertEqual(parse_verdict("CITATION rather than MENTION"), KEEP)

    def test_unusable_replies_are_unknown(self):
        for raw in ("", "   ", "maybe", "__ERROR__ URLError", None):
            self.assertEqual(parse_verdict(raw), UNKNOWN, repr(raw))


class TestFailOpen(unittest.TestCase):
    """An unreachable model must cost precision, never recall."""

    def test_only_a_confident_drop_removes_a_mention(self):
        self.assertTrue(Decision(KEEP, "CITATION").keeps)
        self.assertTrue(Decision(UNKNOWN, "").keeps)
        self.assertFalse(Decision(DROP, "MENTION").keeps)

    def test_error_reply_keeps_the_mention(self):
        self.assertTrue(Decision(parse_verdict("__ERROR__ timeout"), "").keeps)


class TestCache(unittest.TestCase):
    def test_key_depends_on_model_and_prompt(self):
        a = cache_key("m1", "p")
        self.assertEqual(a, cache_key("m1", "p"))
        self.assertNotEqual(a, cache_key("m2", "p"))
        self.assertNotEqual(a, cache_key("m1", "q"))

    def test_roundtrip_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.jsonl"
            cache = Cache(path)
            self.assertIsNone(cache.get("k"))
            cache.put("k", "CITATION", {"article_id": "a"})
            self.assertEqual(Cache(path).get("k"), "CITATION")

    def test_missing_file_is_an_empty_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(Cache(Path(tmp) / "absent.jsonl").get("k"))


class TestPrompt(unittest.TestCase):
    def test_prompt_contains_the_id_and_context(self):
        prompt = build_prompt("IPR000884", "a domain named IPR000884 in the text")
        self.assertIn("IPR000884", prompt)
        self.assertIn("a domain named", prompt)
        self.assertIn("CITATION", prompt)
        self.assertIn("MENTION", prompt)

    def test_context_is_truncated(self):
        prompt = build_prompt("X", "y" * 5000, max_context=100)
        self.assertNotIn("y" * 101, prompt)


if __name__ == "__main__":
    unittest.main()
