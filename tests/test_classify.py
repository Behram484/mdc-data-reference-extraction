"""Unit tests for evidence collection and the Primary/Secondary rule."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mdc.classify import (  # noqa: E402
    PRIMARY,
    SECONDARY,
    classify,
    format_location_type,
    load_prefix_types,
)
from mdc.context import Evidence, collect_evidence  # noqa: E402
from mdc.pipeline import extract_ids  # noqa: E402

JATS = """<?xml version="1.0"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front><article-meta>
    <article-id pub-id-type="doi">10.1234/self.2024</article-id>
  </article-meta></front>
  <body><sec><p>We deposited our measurements at
    <ext-link xlink:href="https://doi.org/10.5061/dryad.abc">Dryad</ext-link>,
    and analysed IPR000884 throughout.</p></sec></body>
  <back><ref-list>
    <ref><element-citation>
      <pub-id pub-id-type="doi">10.15468/reused.data</pub-id>
    </element-citation></ref>
    <ref><element-citation>
      <pub-id pub-id-type="doi">10.1371/journal.pone.1</pub-id>
    </element-citation></ref>
  </ref-list></back>
</article>
"""


def ev(dataset_id: str, main: bool, refs: bool, context: str = "") -> Evidence:
    return Evidence(dataset_id, main, refs, (context,))


class TestEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "a.xml"
        self.path.write_text(JATS, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_location_is_recorded_per_id(self):
        found = collect_evidence(self.path, "10.1234_self.2024", read_references=True)
        self.assertEqual(found["https://doi.org/10.5061/dryad.abc"].location, "main")
        self.assertEqual(
            found["https://doi.org/10.15468/reused.data"].location, "references"
        )

    def test_publisher_doi_in_bibliography_is_filtered_out(self):
        found = collect_evidence(self.path, "10.1234_self.2024", read_references=True)
        self.assertNotIn("https://doi.org/10.1371/journal.pone.1", found)

    def test_context_captures_surrounding_words(self):
        found = collect_evidence(self.path, "10.1234_self.2024")
        self.assertIn("deposited", found["https://doi.org/10.5061/dryad.abc"].joined_context)

    def test_references_are_skipped_when_not_requested(self):
        found = collect_evidence(self.path, "10.1234_self.2024", read_references=False)
        self.assertNotIn("https://doi.org/10.15468/reused.data", found)

    def test_extract_ids_agrees_with_collect_evidence(self):
        """The two entry points must not drift apart."""
        for read_refs in (False, True):
            with self.subTest(read_references=read_refs):
                self.assertEqual(
                    extract_ids(self.path, "10.1234_self.2024", read_references=read_refs),
                    set(collect_evidence(
                        self.path, "10.1234_self.2024", read_references=read_refs
                    )),
                )


class TestFormatLocationRule(unittest.TestCase):
    def test_doi_in_main_text_is_primary(self):
        self.assertEqual(format_location_type(ev("https://doi.org/10.9999/x", True, False)), PRIMARY)

    def test_doi_only_in_bibliography_is_secondary(self):
        self.assertEqual(format_location_type(ev("https://doi.org/10.9999/x", False, True)), SECONDARY)

    def test_doi_in_both_places_is_primary(self):
        self.assertEqual(format_location_type(ev("https://doi.org/10.9999/x", True, True)), PRIMARY)

    def test_accession_is_secondary(self):
        self.assertEqual(format_location_type(ev("IPR000884", True, False)), SECONDARY)


class TestClassify(unittest.TestCase):
    def test_learned_prefix_overrides_the_generic_rule(self):
        types = {"10.15468": SECONDARY}
        target = ev("https://doi.org/10.15468/x", True, False)
        self.assertEqual(format_location_type(target), PRIMARY)
        self.assertEqual(classify(target, types), SECONDARY)

    def test_unknown_prefix_falls_back(self):
        self.assertEqual(classify(ev("https://doi.org/10.9999/x", True, False), {}), PRIMARY)

    def test_accessions_are_unaffected_by_prefix_types(self):
        self.assertEqual(classify(ev("IPR000884", True, False), {"10.5061": PRIMARY}), SECONDARY)

    def test_learned_table_was_generated_and_matches_the_labels(self):
        types = load_prefix_types()
        self.assertTrue(types, "run scripts/build_prefix_types.py")
        self.assertEqual(types.get("10.5061"), PRIMARY)     # Dryad, 65-0 in dev
        self.assertEqual(types.get("10.3886"), SECONDARY)   # ICPSR, 0-18 in dev


if __name__ == "__main__":
    unittest.main()
