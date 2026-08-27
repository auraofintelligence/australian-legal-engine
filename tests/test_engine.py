"""Tests for the engine, including a golden set over real acts.

The unit tests run anywhere. The golden set needs the 2012 corpus on disk
and is skipped without it, because a test that quietly passes when its
subject is missing is worse than no test.

Run with:  python tests/test_engine.py
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import (answer, extract, index as index_module, parse, profiles,  # noqa: E402
                    textclean, threads)

CORPUS = os.environ.get(
    "LEGAL_CORPUS",
    r"C:\Users\sbt41\Downloads\Australian Law 2012 - Lukes Relevance")

PRIVACY = os.path.join(CORPUS, "Australian Privacy Act 1988.pdf")
TENANCY = os.path.join(
    CORPUS, "QLD - Residential Tenancies and Rooming Accommodation Act 2008.pdf")

HAVE_CORPUS = os.path.exists(PRIVACY) and os.path.exists(TENANCY)


class TestTextClean(unittest.TestCase):
    def test_repairs_mangled_apostrophe(self):
        self.assertEqual(textclean.clean("person\ufffds place"), "person's place")

    def test_repairs_mangled_dash(self):
        self.assertEqual(textclean.clean("other than\ufffd"), "other than-")

    def test_keeps_line_structure(self):
        self.assertEqual(textclean.clean("(1) one\n(2) two"), "(1) one\n(2) two")

    def test_rejoins_hyphen_split_word(self):
        self.assertEqual(textclean.clean("sub-\nsection"), "subsection")

    def test_collapse_flattens(self):
        self.assertEqual(textclean.collapse("a\n  b   c"), "a b c")

    def test_rejoins_words_split_by_extraction(self):
        vocabulary = textclean.build_vocabulary("police " * 9 + "evidence " * 9)
        self.assertEqual(
            textclean.rejoin_split_words("the polic e found eviden ce",
                                         vocabulary),
            "the police found evidence")

    def test_leaves_ordinary_word_pairs_alone(self):
        # "maybe" is a real word, but "may" is common on its own, so the
        # pair must survive untouched.
        vocabulary = textclean.build_vocabulary(
            "maybe " * 9 + "may " * 40 + "be " * 40)
        self.assertEqual(
            textclean.rejoin_split_words("it may be so", vocabulary),
            "it may be so")

    def test_leaves_rare_joins_alone(self):
        vocabulary = textclean.build_vocabulary("polic e")
        self.assertEqual(
            textclean.rejoin_split_words("polic e", vocabulary), "polic e")


class TestProfiles(unittest.TestCase):
    def test_detects_queensland_from_section_marker(self):
        self.assertEqual(profiles.detect("[s 35]\nsomething").key, "qld")

    def test_detects_commonwealth_from_comlaw_note(self):
        self.assertEqual(
            profiles.detect("ComLaw Authoritative Act C2012C00903").key, "cth")

    def test_unknown_source_falls_back_to_generic(self):
        self.assertEqual(profiles.detect("a page of prose").key, "generic")

    def test_section_start_matches_both_layouts(self):
        self.assertTrue(profiles.QUEENSLAND.section_start.match(
            "35 Rental purchase plan agreements"))
        self.assertTrue(profiles.COMMONWEALTH.section_start.match(
            "6  Interpretation"))


class TestAddresses(unittest.TestCase):
    def test_subsection_address_reads_like_a_citation(self):
        provision = parse.Provision(
            kind="subsection", number="2", heading="", text="x",
            act="Privacy Act 1988", jurisdiction="Commonwealth",
            section="13", subsection="2")
        self.assertEqual(provision.address, "Privacy Act 1988 s 13(2)")

    def test_paragraph_address_nests(self):
        provision = parse.Provision(
            kind="paragraph", number="a", heading="", text="x",
            act="Privacy Act 1988", jurisdiction="Commonwealth",
            section="13", subsection="2", paragraph="a")
        self.assertEqual(provision.address, "Privacy Act 1988 s 13(2)(a)")

    def test_context_shows_the_tree(self):
        provision = parse.Provision(
            kind="section", number="13", heading="", text="x",
            act="A", jurisdiction="Commonwealth", part="III", division="1",
            section="13")
        self.assertEqual(provision.context, "Part III > Division 1")


class TestPacket(unittest.TestCase):
    def _packet(self) -> answer.Packet:
        return answer.Packet(
            question="what does it say",
            extracts=[answer.Extract(
                address="Privacy Act 1988 s 13", context="Part III",
                heading="Interferences with privacy", text="Some text.",
                jurisdiction="Commonwealth", currency="11 December 2012",
                source="x.pdf", score=1.0, reasons=["test"])],
            notes=["a note"])

    def test_prompt_forbids_invented_citations(self):
        prompt = self._packet().as_prompt()
        self.assertIn("Do not name any section", prompt)
        self.assertIn("Privacy Act 1988 s 13", prompt)
        self.assertIn("legal information, not legal advice", prompt.lower())

    def test_prompt_carries_the_register_for_checking(self):
        self.assertIn("legislation.gov.au", self._packet().as_prompt())

    def test_empty_packet_refuses_to_answer(self):
        empty = answer.Packet(question="q", extracts=[], notes=[])
        self.assertFalse(empty.found)
        self.assertIn("will not answer", empty.as_text())


@unittest.skipUnless(HAVE_CORPUS, "2012 corpus not on this machine")
class TestGoldenSet(unittest.TestCase):
    """Questions with citations checked by reading the source acts.

    Each expectation below was verified against the 2012 text itself. They
    describe those documents as they stood on their printed currency dates,
    not the law today.
    """

    index: index_module.Index

    @classmethod
    def setUpClass(cls) -> None:
        cls.index = index_module.build([PRIVACY, TENANCY])

    def assert_cites(self, question: str, act_fragment: str, section: str,
                     limit: int = 5) -> None:
        packet = answer.ask(self.index, question, limit=limit)
        self.assertTrue(packet.found, f"no provisions returned for: {question}")
        addresses = [extract.address for extract in packet.extracts]
        matched = any(act_fragment.lower() in address.lower()
                      and f"s {section}" in address for address in addresses)
        self.assertTrue(
            matched,
            f"expected {act_fragment} s {section} in the top {limit} for "
            f"'{question}', got: {addresses}")

    # --- retrieval ----------------------------------------------------

    def test_entry_notice_finds_the_notice_of_entry_section(self):
        self.assert_cites("notice of entry period",
                          "Residential Tenancies", "193")

    def test_unlawful_entry_is_found_by_plain_words(self):
        self.assert_cites("entry to the premises by the lessor",
                          "Residential Tenancies", "202")

    def test_interference_with_privacy_is_found(self):
        self.assert_cites("act or practice that interferes with privacy",
                          "Privacy Act", "13")

    def test_objects_clause_is_reachable(self):
        self.assert_cites("objects of the Act", "Residential Tenancies", "5")

    # --- citation lookup ----------------------------------------------

    def test_citation_lookup_returns_the_named_section(self):
        packet = answer.cite(self.index, "Privacy Act", "13")
        self.assertTrue(packet.found)
        self.assertTrue(packet.extracts[0].address.startswith("Privacy Act 1988 s 13"))

    def test_citation_lookup_of_a_missing_section_refuses(self):
        packet = answer.cite(self.index, "Privacy Act", "99999")
        self.assertFalse(packet.found)
        self.assertIn("No provision", packet.as_text())

    # --- provenance ---------------------------------------------------

    def test_every_extract_carries_an_address(self):
        packet = answer.ask(self.index, "rental bond", limit=5)
        for item in packet.extracts:
            self.assertTrue(item.address.strip())
            self.assertIn(" s ", item.address)

    def test_currency_dates_come_from_the_sources(self):
        packet = answer.ask(self.index, "rental bond", limit=3)
        for item in packet.extracts:
            self.assertEqual(item.currency, "17 September 2012")

    def test_notes_always_say_it_is_not_advice(self):
        packet = answer.ask(self.index, "rental bond", limit=2)
        self.assertTrue(any("not legal advice" in note for note in packet.notes))

    def test_jurisdiction_filter_excludes_other_parliaments(self):
        packet = answer.ask(self.index, "notice", limit=5,
                            jurisdiction="Commonwealth")
        for item in packet.extracts:
            self.assertEqual(item.jurisdiction, "Commonwealth")

    # --- parsing ------------------------------------------------------

    def test_titles_come_from_the_acts_not_the_filenames(self):
        titles = {source["act"] for source in self.index.sources}
        self.assertIn("Privacy Act 1988", titles)
        self.assertIn(
            "Residential Tenancies and Rooming Accommodation Act 2008", titles)

    def test_contents_pages_are_not_indexed_as_provisions(self):
        # A contents entry would carry a dot leader into the text.
        for record in self.index.records:
            self.assertNotIn("....", record.text)

    def test_running_header_does_not_leak_into_provisions(self):
        # The act's own title on its own line is a page header, not law.
        for record in self.index.records:
            self.assertNotIn("Privacy Act 1988 Privacy Act 1988", record.text)
            self.assertNotEqual(record.text.strip(), record.act.strip())

    def test_unreadable_document_is_recorded_not_fatal(self):
        index = index_module.build([PRIVACY, os.path.join(CORPUS, "nope.pdf")])
        self.assertEqual(len(index.skipped), 1)
        self.assertTrue(index.records, "the readable document still indexed")

    def test_queensland_reprint_warning_is_surfaced(self):
        tenancy = [source for source in self.index.sources
                   if "Residential Tenancies" in source["act"]][0]
        self.assertTrue(any("not an authorised copy" in warning
                            for warning in tenancy["warnings"]))


class TestThreads(unittest.TestCase):
    def _record(self, text: str, act: str = "Privacy Act 1988",
                section: str = "13") -> index_module.Record:
        return index_module.Record(
            uid="0", text=text, address=f"{act} s {section}", act=act,
            jurisdiction="Commonwealth", kind="subsection", section=section,
            subsection="1", paragraph="", context="", heading="",
            currency="11 December 2012", page=1, source="x.pdf")

    def test_finds_a_reference_to_another_act(self):
        record = self._record(
            "notice given in accordance with section 157 of the Personal "
            "Property Securities Act 2009")
        edges = threads.extract_edges(record, {"Privacy Act 1988"})
        self.assertTrue(edges)
        self.assertEqual(edges[0].target_act, "Personal Property Securities Act 2009")
        self.assertEqual(edges[0].target_section, "157")

    def test_keeps_lowercase_words_inside_an_act_name(self):
        record = self._record("as defined in the Freedom of Information Act 1982")
        edges = threads.extract_edges(record, {"Privacy Act 1988"})
        self.assertEqual(edges[0].target_act, "Freedom of Information Act 1982")

    def test_reference_within_the_same_act_keeps_the_act(self):
        record = self._record("breaches a guideline under section 17")
        edges = threads.extract_edges(record, {"Privacy Act 1988"})
        self.assertEqual(edges[0].target_act, "Privacy Act 1988")
        self.assertEqual(edges[0].target_section, "17")

    def test_self_reference_is_not_a_thread(self):
        record = self._record("for the purposes of section 13", section="13")
        self.assertEqual(threads.extract_edges(record, set()), [])

    def test_relation_is_named_from_the_drafters_words(self):
        record = self._record("This section is subject to section 20")
        self.assertEqual(threads.extract_edges(record, set())[0].relation,
                         "subject to")

    def test_every_edge_carries_the_words_it_came_from(self):
        record = self._record("see section 20 of the Crimes Act 1914")
        for edge in threads.extract_edges(record, set()):
            self.assertIn("section 20", edge.quote)

    def test_wrapped_title_counts_as_the_same_act(self):
        self.assertTrue(threads._same_act(
            "Rooming Accommodation Act 2008",
            "Residential Tenancies and Rooming Accommodation Act 2008"))
        self.assertTrue(threads._same_act("the Privacy Act 1988", "Privacy Act 1988"))
        self.assertFalse(threads._same_act("Crimes Act 1914", "Privacy Act 1988"))


@unittest.skipUnless(HAVE_CORPUS, "2012 corpus not on this machine")
class TestThreadsOverRealActs(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = index_module.build([PRIVACY])
        cls.map = threads.build(cls.index)

    def test_privacy_act_points_at_the_acts_interpretation_act(self):
        targets = {edge.target_act for edge in self.map.edges}
        self.assertIn("Acts Interpretation Act 1901", targets)

    def test_reading_list_excludes_acts_already_indexed(self):
        listed = {act for act, _, _ in self.map.reading_list()}
        self.assertNotIn("Privacy Act 1988", listed)
        self.assertTrue(listed, "the Privacy Act does point at other acts")

    def test_reading_list_entries_name_where_they_came_from(self):
        for act, count, examples in self.map.reading_list()[:5]:
            self.assertGreaterEqual(count, 1)
            self.assertTrue(examples[0].strip())


class TestExtractionGuards(unittest.TestCase):
    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            extract.load("no/such/file.pdf")


if __name__ == "__main__":
    unittest.main(verbosity=2)
