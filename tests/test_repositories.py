"""Unit tests for the DOI prefix allowlist."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mdc.repositories import (  # noqa: E402
    APRIORI_PREFIXES,
    allowed_prefixes,
    doi_prefix,
    is_data_doi,
    learned_prefixes,
)


class TestDoiPrefix(unittest.TestCase):
    def test_extracts_the_registrant(self):
        self.assertEqual(doi_prefix("https://doi.org/10.5061/dryad.886pr72"), "10.5061")
        self.assertEqual(doi_prefix("https://doi.org/10.15468/dl.abc/def"), "10.15468")

    def test_non_doi_ids_have_no_prefix(self):
        for value in ("IPR000884", "", "10.5061/dryad.x", "PRJNA10687"):
            self.assertEqual(doi_prefix(value), "", value)


class TestAllowlist(unittest.TestCase):
    def test_learned_list_was_generated(self):
        self.assertTrue(learned_prefixes(), "run scripts/build_allowlist.py")

    def test_known_data_repositories_pass(self):
        for prefix in ("10.5061", "10.5281", "10.15468", "10.1594"):
            self.assertIn(prefix, allowed_prefixes(), prefix)

    def test_publisher_and_funder_dois_are_rejected(self):
        """The four biggest S2 error sources, by false-positive count."""
        for prefix, what in (
            ("10.13039", "Crossref Funder Registry, 221 false positives"),
            ("10.1371", "PLOS, 123"),
            ("10.1107", "IUCr, 79"),
            ("10.7554", "eLife, 51"),
        ):
            with self.subTest(what):
                self.assertFalse(is_data_doi(f"https://doi.org/{prefix}/x"), what)

    def test_figshare_and_ccdc_are_excluded_despite_being_repositories(self):
        """223 and 75 annotator-rejected candidates, zero real citations."""
        self.assertNotIn("10.6084", allowed_prefixes())
        self.assertNotIn("10.5517", allowed_prefixes())

    def test_accession_ids_are_never_filtered(self):
        """Prefix filtering is a DOI concept; accessions are already specific."""
        for value in ("IPR000884", "PRJNA10687", "EPI_ISL_291131"):
            self.assertTrue(is_data_doi(value), value)

    def test_apriori_prefixes_are_always_allowed(self):
        for prefix in APRIORI_PREFIXES:
            self.assertTrue(is_data_doi(f"https://doi.org/{prefix}/x"), prefix)

    def test_explicit_allowlist_argument_overrides(self):
        self.assertTrue(is_data_doi("https://doi.org/10.9999/x", frozenset({"10.9999"})))
        self.assertFalse(is_data_doi("https://doi.org/10.5061/x", frozenset({"10.9999"})))


if __name__ == "__main__":
    unittest.main()
