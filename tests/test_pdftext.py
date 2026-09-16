"""Unit tests for the PDF backend and the format dispatcher.

No PDF is parsed here: pypdf is an optional dependency and the XML path -- 76%
of the corpus and every stage up to S5 -- has to keep working without it. What
is covered is the logic that decides where the bibliography starts and rejoins
identifiers broken by line wrapping, which is where PDF-specific bugs live.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mdc.document import parse_segments, self_doi_candidates  # noqa: E402
from mdc.dois import find_dois  # noqa: E402
from mdc.pdftext import _dewrap, split_sections  # noqa: E402
from mdc.xmltext import MAIN, REFERENCES  # noqa: E402

try:
    import pypdf  # noqa: F401

    HAVE_PYPDF = True
except ImportError:
    HAVE_PYPDF = False

JATS = """<?xml version="1.0"?>
<article><front><article-meta>
  <article-id pub-id-type="doi">10.1234/self.2024</article-id>
</article-meta></front>
<body><p>data at https://doi.org/10.5061/dryad.abc</p></body></article>
"""


class TestSectionSplit(unittest.TestCase):
    def test_splits_on_a_standalone_heading(self):
        main, refs = split_sections("body text\nReferences\nSmith 2020\nJones 2019")
        self.assertIn("body text", main)
        self.assertNotIn("Smith 2020", main)
        self.assertIn("Smith 2020", refs)

    def test_accepts_the_usual_heading_spellings(self):
        for heading in (
            "References", "REFERENCES", "Bibliography",
            "Literature Cited", "7. References", "References:",
        ):
            with self.subTest(heading):
                main, refs = split_sections(f"body\n{heading}\nSmith 2020")
                self.assertIn("Smith 2020", refs, heading)

    def test_the_word_in_running_text_is_not_a_heading(self):
        text = "we compared references to the earlier survey and found agreement"
        main, refs = split_sections(text)
        self.assertEqual(refs, "")
        self.assertEqual(main, text)

    def test_uses_the_last_heading_not_the_first(self):
        """A table of contents names the section long before it begins."""
        main, refs = split_sections("Contents\nReferences\n\nIntro body\nReferences\nSmith 2020")
        self.assertIn("Intro body", main)
        self.assertIn("Smith 2020", refs)

    def test_heading_at_the_very_end_is_treated_as_an_artefact(self):
        main, refs = split_sections("a very long body " * 50 + "\nReferences\n")
        self.assertEqual(refs, "")

    def test_no_heading_means_everything_is_main(self):
        main, refs = split_sections("body only, no bibliography")
        self.assertEqual(refs, "")


class TestDewrap(unittest.TestCase):
    def test_rejoins_a_doi_split_across_lines(self):
        self.assertEqual(
            find_dois(_dewrap("see 10.5061/dry\nad.abc for data")),
            {"https://doi.org/10.5061/dryad.abc"},
        )

    def test_drops_a_hyphen_introduced_by_wrapping(self):
        self.assertEqual(
            find_dois(_dewrap("see 10.5061/dry-\nad.abc here")),
            {"https://doi.org/10.5061/dryad.abc"},
        )

    def test_handles_a_doi_broken_more_than_once(self):
        self.assertEqual(
            find_dois(_dewrap("10.5061/dr\nya\nd.abc")),
            {"https://doi.org/10.5061/dryad.abc"},
        )

    def test_ordinary_prose_is_untouched(self):
        text = "the first line\nthe second line"
        self.assertEqual(_dewrap(text), text)


class TestDispatcher(unittest.TestCase):
    def test_xml_still_routes_to_the_xml_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.xml"
            path.write_text(JATS, encoding="utf-8")
            segments = parse_segments(path)
            self.assertTrue(segments)
            self.assertEqual({s.section for s in segments}, {MAIN})
            self.assertEqual(self_doi_candidates(path), {"10.1234/self.2024"})

    def test_pdf_has_no_machine_readable_self_doi(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.pdf"
            path.write_bytes(b"%PDF-1.4 not really a pdf")
            self.assertEqual(self_doi_candidates(path), set())

    @unittest.skipUnless(HAVE_PYPDF, "pypdf is an optional dependency")
    def test_unreadable_pdf_yields_no_segments_rather_than_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.pdf"
            path.write_bytes(b"%PDF-1.4 truncated")
            self.assertEqual(parse_segments(path), [])


if __name__ == "__main__":
    unittest.main()
