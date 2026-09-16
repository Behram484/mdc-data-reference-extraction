"""Unit tests for the accession patterns and the format-prior type rule."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mdc.accessions import (  # noqa: E402
    ALL,
    BY_NAME,
    SELECTED,
    find_accessions,
    find_by_pattern,
    resolve,
)
from mdc.pipeline import PRIMARY, SECONDARY, format_prior_type  # noqa: E402

# one real gold id per selected pattern, taken from train_labels.csv
GOLD_EXAMPLES = {
    "gisaid_epi": "EPI1018205",
    "chembl": "CHEMBL1257578",
    "interpro": "IPR000884",
    "gisaid_isl": "EPI_ISL_291131",
    "arrayexpress": "E-PROT-100",
    "pfam": "PF00348",
    "cellosaurus": "CVCL_0213",
    "pride": "PXD001676",
    "bioproject": "PRJNA10687",
    "kegg_ortholog": "K02388",
    "biosample": "SAMN07159041",
    "ensembl": "ENSBTAG00000011038",
}


class TestSelectedPatterns(unittest.TestCase):
    def test_every_selected_pattern_matches_its_gold_example(self):
        for name, example in GOLD_EXAMPLES.items():
            with self.subTest(name):
                self.assertTrue(BY_NAME[name].regex.fullmatch(example), example)

    def test_selection_covers_exactly_the_documented_names(self):
        self.assertEqual({p.name for p in SELECTED}, set(GOLD_EXAMPLES))

    def test_all_selected_ids_are_found_in_running_text(self):
        text = "We deposited " + ", ".join(GOLD_EXAMPLES.values()) + " in public repositories."
        self.assertEqual(find_accessions(text, SELECTED), set(GOLD_EXAMPLES.values()))

    def test_ids_are_emitted_verbatim_not_case_folded(self):
        """Gold contains both 5VA1 and 2nrj, so case must survive."""
        self.assertEqual(find_accessions("IPR000884", SELECTED), {"IPR000884"})


class TestPatternBoundaries(unittest.TestCase):
    def test_pattern_does_not_fire_inside_a_longer_token(self):
        for text in ("XIPR000884", "IPR000884X", "abc/IPR000884", "IPR000884-extra"):
            with self.subTest(text):
                self.assertEqual(find_accessions(text, SELECTED), set(), text)

    def test_pattern_fires_next_to_ordinary_punctuation(self):
        for text in ("(IPR000884)", "IPR000884.", "see IPR000884, and", "[IPR000884]"):
            with self.subTest(text):
                self.assertEqual(find_accessions(text, SELECTED), {"IPR000884"}, text)


class TestRiskyPatterns(unittest.TestCase):
    """The rejected patterns are kept in the registry; these show why."""

    def test_cath_cannot_be_told_from_a_version_number(self):
        self.assertIn("1.2.3.4", find_by_pattern("version 1.2.3.4", ALL)["cath"])

    def test_pdb_matches_ordinary_text(self):
        """A 4-char code of digit + alphanumerics is indistinguishable from prose."""
        hits = find_by_pattern("after a 5min incubation", ALL)["pdb"]
        self.assertEqual(hits, {"5min"})

    def test_risky_patterns_are_not_in_the_selected_set(self):
        for name in ("pdb", "cath", "genbank", "geo", "refseq", "dbsnp", "uniprot"):
            self.assertNotIn(name, {p.name for p in SELECTED}, name)


class TestResolve(unittest.TestCase):
    def test_keywords(self):
        self.assertEqual(resolve("selected"), SELECTED)
        self.assertEqual(resolve(""), SELECTED)
        self.assertEqual(resolve("all"), ALL)
        self.assertEqual(resolve("none"), ())

    def test_explicit_names(self):
        self.assertEqual([p.name for p in resolve("interpro,pfam")], ["interpro", "pfam"])

    def test_unknown_name_is_rejected(self):
        with self.assertRaises(KeyError):
            resolve("interpro,not_a_repository")


class TestFormatPrior(unittest.TestCase):
    def test_doi_is_primary_and_accession_is_secondary(self):
        self.assertEqual(format_prior_type("https://doi.org/10.5061/dryad.x"), PRIMARY)
        self.assertEqual(format_prior_type("IPR000884"), SECONDARY)


if __name__ == "__main__":
    unittest.main()
