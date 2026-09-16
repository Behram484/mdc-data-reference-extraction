"""Unit tests for DOI normalisation and schema-agnostic XML text extraction."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mdc.dois import (  # noqa: E402
    article_id_to_doi,
    drop_self_citations,
    find_dois,
    normalize_doi,
)
from mdc.xmltext import (  # noqa: E402
    MAIN,
    REFERENCES,
    parse_segments,
    section_text,
    self_doi_candidates,
)

JATS = """<?xml version="1.0"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front><article-meta>
    <article-id pub-id-type="pmid">12345</article-id>
    <article-id pub-id-type="doi">10.1234/self.2024</article-id>
  </article-meta></front>
  <body>
    <sec><p>Data are at <ext-link xlink:href="https://doi.org/10.5061/dryad.abc">Dryad</ext-link>
    and doi:10.5281/zenodo.99.</p></sec>
  </body>
  <back><ref-list>
    <ref><element-citation><pub-id pub-id-type="doi">10.9999/cited.paper</pub-id></element-citation></ref>
  </ref-list></back>
</article>
"""

TEI = """<?xml version="1.0"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text><body><p>See <ptr target="https://doi.org/10.17882/49388"/> for the data.</p></body>
  <back><div type="references"><listBibl>
    <biblStruct><idno type="DOI">10.9999/cited.paper</idno></biblStruct>
  </listBibl></div></back></text>
</TEI>
"""


def write(tmp: str, name: str, content: str) -> Path:
    p = Path(tmp) / name
    p.write_text(content, encoding="utf-8")
    return p


class TestNormalizeDoi(unittest.TestCase):
    def test_all_surface_forms_collapse_to_one(self):
        expected = "https://doi.org/10.5061/dryad.abc"
        for raw in (
            "10.5061/dryad.abc",
            "doi:10.5061/dryad.abc",
            "DOI: 10.5061/dryad.abc",
            "https://doi.org/10.5061/dryad.abc",
            "http://dx.doi.org/10.5061/dryad.abc",
            "www.doi.org/10.5061/dryad.abc",
            "(10.5061/dryad.abc)",
        ):
            self.assertEqual(normalize_doi(raw), expected, raw)

    def test_case_is_folded(self):
        self.assertEqual(normalize_doi("10.1234/ABC-Def"), "https://doi.org/10.1234/abc-def")

    def test_sentence_punctuation_is_stripped(self):
        for raw in ("10.1234/abc.", "10.1234/abc,", "10.1234/abc;", "10.1234/abc'"):
            self.assertEqual(normalize_doi(raw), "https://doi.org/10.1234/abc", raw)

    def test_balanced_brackets_survive(self):
        """10.1016/S0967-0637(01)00025-5 is a real DOI; the parens are part of it."""
        self.assertEqual(
            normalize_doi("10.1016/S0967-0637(01)00025-5."),
            "https://doi.org/10.1016/s0967-0637(01)00025-5",
        )

    def test_unbalanced_closing_paren_is_dropped(self):
        self.assertEqual(normalize_doi("(10.1234/abc)"), "https://doi.org/10.1234/abc")

    def test_non_dois_are_rejected(self):
        for raw in ("", "not a doi", "10.123/tooshortprefix", "10.1234/", "doi:"):
            self.assertIsNone(normalize_doi(raw), raw)


class TestSelfDoi(unittest.TestCase):
    def test_article_id_maps_on_first_underscore_only(self):
        self.assertEqual(article_id_to_doi("10.1002_2017jc013030"), "10.1002/2017jc013030")
        self.assertEqual(
            article_id_to_doi("10.1051_e3sconf_202017220004"),
            "10.1051/e3sconf_202017220004",
        )

    def test_underscore_slash_ambiguity_still_matches(self):
        """23 of 523 ids have extra underscores; '_' and '/' must compare equal."""
        kept = drop_self_citations(
            {"https://doi.org/10.1051/e3sconf/202017220004", "https://doi.org/10.5061/dryad.x"},
            {"10.1051/e3sconf_202017220004"},
        )
        self.assertEqual(kept, {"https://doi.org/10.5061/dryad.x"})


class TestXmlText(unittest.TestCase):
    def test_jats_splits_body_from_reference_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            segs = parse_segments(write(tmp, "a.xml", JATS))
            main = find_dois(section_text(segs, {MAIN}))
            refs = find_dois(section_text(segs, {REFERENCES}))
            self.assertIn("https://doi.org/10.5061/dryad.abc", main)
            self.assertIn("https://doi.org/10.5281/zenodo.99", main)
            self.assertNotIn("https://doi.org/10.9999/cited.paper", main)
            self.assertIn("https://doi.org/10.9999/cited.paper", refs)

    def test_tei_splits_body_from_reference_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            segs = parse_segments(write(tmp, "b.xml", TEI))
            main = find_dois(section_text(segs, {MAIN}))
            self.assertIn("https://doi.org/10.17882/49388", main)
            self.assertNotIn("https://doi.org/10.9999/cited.paper", main)

    def test_dois_in_link_attributes_are_found(self):
        """563 of the DOI hits in a 60-file sample were in ptr@target alone."""
        with tempfile.TemporaryDirectory() as tmp:
            segs = parse_segments(write(tmp, "c.xml", TEI))
            self.assertIn("https://doi.org/10.17882/49388", find_dois(section_text(segs)))

    def test_self_doi_comes_from_metadata_not_the_bibliography(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                self_doi_candidates(write(tmp, "a.xml", JATS)), {"10.1234/self.2024"}
            )
            # TEI <idno type="DOI"> lives inside every biblStruct -- must not leak
            self.assertEqual(self_doi_candidates(write(tmp, "b.xml", TEI)), set())

    def test_segments_are_not_welded_together(self):
        """Joining fragments without a space would manufacture ids."""
        xml = "<r><a>10.1234/abc</a><b>10.5678/def</b></r>"
        with tempfile.TemporaryDirectory() as tmp:
            text = section_text(parse_segments(write(tmp, "d.xml", xml)))
            self.assertEqual(
                find_dois(text),
                {"https://doi.org/10.1234/abc", "https://doi.org/10.5678/def"},
            )

    def test_unparseable_xml_returns_empty_not_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "bad.xml", "<a><unclosed>")
            self.assertEqual(parse_segments(p), [])
            self.assertEqual(self_doi_candidates(p), set())


if __name__ == "__main__":
    unittest.main()
