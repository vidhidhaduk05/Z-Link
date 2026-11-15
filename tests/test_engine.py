"""
Integration and Unit Tests for Reference Parsing, Reachability Validation, and Field Injection.
"""
import os
import sys
import unittest
import docx
import re
from io import BytesIO
from lxml import etree
from docx.oxml.ns import qn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server.parser import parse_docx_manuscript, parse_paragraphs_list
from server.validator import validate_single_reference, map_usage_and_sequence
from server.ris_generator import generate_ris
from server.linker import link_docx_manuscript
from server.models import ReferenceEntry

class TestZoteroLinkEngine(unittest.TestCase):
    docx_file = "sample_radiology_manuscript.docx"

    def test_01_parser(self):
        paras, sites, references = parse_docx_manuscript(self.docx_file)
        self.assertGreaterEqual(len(references), 5, "Should extract at least 5 references")
        self.assertEqual(references[0].ref_num, 1)
        self.assertIn("10.1038/s41586-020-2649-2", references[0].doi)
        
        # Verify citation sites
        self.assertGreaterEqual(len(sites), 4, "Should find at least 4 citation sites")
        all_cited_nums = set()
        for s in sites:
            all_cited_nums.update(s.nums)
        self.assertTrue({1, 2, 3, 4, 5}.issubset(all_cited_nums), "All references 1-5 should be cited")

    def test_02_usage_mapping(self):
        paras, sites, references = parse_docx_manuscript(self.docx_file)
        ref_map, seq_valid, warnings = map_usage_and_sequence(references, sites)
        self.assertTrue(seq_valid, "Initial citations should be in consecutive order")
        self.assertIn(1, ref_map)
        self.assertGreaterEqual(ref_map[1].total_occurrences, 2, "Reference 1 should occur multiple times")
        self.assertTrue(len(ref_map[1].first_mention_sentence) > 10)

    def test_03_reachability_and_broken_detection(self):
        paras, sites, references = parse_docx_manuscript(self.docx_file)
        
        # Ref 1 is NumPy (Valid Nature DOI)
        v1 = validate_single_reference(references[0])
        self.assertTrue(v1.is_reachable, "NumPy DOI should be reachable")
        self.assertEqual(v1.status, "verified")
        self.assertIn("NumPy", v1.crossref_title or references[0].title)

        # Ref 4 is deliberately invalid DOI
        v4 = validate_single_reference(references[3])
        self.assertFalse(v4.is_reachable, "Broken DOI should fail reachability")
        self.assertEqual(v4.status, "unreachable")

    def test_04_ris_generation(self):
        paras, sites, references = parse_docx_manuscript(self.docx_file)
        ris_text = generate_ris(references)
        self.assertIn("TY  - JOUR", ris_text)
        self.assertIn("10.1038/s41586-020-2649-2", ris_text)
        self.assertIn("ER  - ", ris_text)

    def test_05_docx_linking(self):
        paras, sites, references = parse_docx_manuscript(self.docx_file)
        out_file = "sample_radiology_linked.docx"
        link_docx_manuscript(self.docx_file, sites, references, output_target=out_file)
        self.assertTrue(os.path.exists(out_file))

        # Inspect resulting XML for Zotero field instructions
        out_doc = docx.Document(out_file)
        xml_str = "".join([p._p.xml for p in out_doc.paragraphs])
        self.assertIn("ADDIN ZOTERO_ITEM", xml_str, "Output must contain native ZOTERO_ITEM fields")
        self.assertIn("ADDIN ZOTERO_BIBL", xml_str, "Output must contain ZOTERO_BIBL field")
        self.assertIn("ADDIN ZOTERO_PREF_1", xml_str, "Output must contain ZOTERO_PREF_1 preferences")

    def test_06_citation_vs_number_discrimination(self):
        from server.parser import parse_paragraphs_list
        test_paras = [
            "INTRODUCTION",
            "Deep learning has improved image diagnosis (1, 2).",
            "We evaluated stage (1) tumors across 45 patients with mean volume of 15 cm3.",
            "Results demonstrated statistical significance (p < 0.05, 95% CI: 1.2-3.4) with R2 of 0.88.",
            "Earlier findings supported this hypothesis (3).",
            "REFERENCES",
            "1. First Author. Title 1. Journal. 2020. doi: 10.1038/s41586-020-2649-2",
            "2. Second Author. Title 2. Journal. 2021. doi: 10.1056/NEJMoa2002032",
            "3. Third Author. Title 3. Journal. 2022. doi: 10.1038/nature12373"
        ]
        paras, sites, refs = parse_paragraphs_list(test_paras)
        cited_nums = []
        for s in sites:
            cited_nums.extend(s.nums)
        
        # Should detect citations (1, 2) and (3)
        self.assertEqual(cited_nums, [1, 2, 3])
        # Verify that "stage (1)", "45 patients", "15 cm3", "p < 0.05", "R2" were NEVER matched as citations
        self.assertEqual(len(sites), 2, "Should only find the 2 actual bibliographic citation sites")

    def test_07_bracket_and_format_selection(self):
        from server.parser import parse_paragraphs_list
        bracket_paras = [
            "INTRODUCTION",
            "Vancouver style uses square brackets [1, 2] and range brackets [3-5].",
            "This document uses only square brackets for references.",
            "REFERENCES",
            "1. First Author. Article 1. 2020. doi: 10.1038/s41586-020-2649-2",
            "2. Second Author. Article 2. 2021. doi: 10.1056/NEJMoa2002032",
            "3. Third Author. Article 3. 2022. doi: 10.1038/nature12373",
            "4. Fourth Author. Article 4. 2023. doi: 10.1038/nature12374",
            "5. Fifth Author. Article 5. 2024. doi: 10.1038/nature12375"
        ]
        
        # Test bracket-specific mode
        paras, sites_bracket, refs = parse_paragraphs_list(bracket_paras, citation_format="bracket")
        nums = []
        for s in sites_bracket:
            nums.extend(s.nums)
        self.assertEqual(nums, [1, 2, 3, 4, 5])
        self.assertTrue(all(s.kind == "bracket" for s in sites_bracket))

        # Test paren-specific mode (should ignore square brackets [1, 2] and [3-5])
        paras, sites_paren, refs = parse_paragraphs_list(bracket_paras, citation_format="paren")
        self.assertEqual(len(sites_paren), 0, "Paren mode should not match square bracket citations")

    def test_08_acta2_real_world_manuscript(self):
        doc_path = "/home/vd00026/Desktop/Zotero_Link/ACTA2_Manuscript_11.14.2026.docx"
        if not os.path.exists(doc_path):
            self.skipTest("ACTA2 manuscript file not present")

        paras, sites, refs = parse_docx_manuscript(doc_path)
        self.assertEqual(len(refs), 43, "ACTA2 manuscript must have exactly 43 references")
        self.assertGreaterEqual(len(sites), 30, "Must detect all in-text citation sites")

        all_cited_nums = set()
        for s in sites:
            all_cited_nums.update(s.nums)
        
        # Verify 100% of all 43 references are cited
        missing = set(range(1, 44)) - all_cited_nums
        self.assertEqual(len(missing), 0, f"All 43 references must be cited in text, missing: {missing}")

        # Verify AMA consecutive sequence
        ref_map, seq_valid, warnings = map_usage_and_sequence(refs, sites)
        self.assertTrue(seq_valid, f"AMA consecutive sequence must be valid, warnings: {warnings}")
        self.assertEqual(len(warnings), 0, "Must have zero sequence warnings")

        # Verify RIS generation
        ris = generate_ris(refs)
        self.assertEqual(ris.count("ER  -"), 43, "RIS must have 43 complete entries")

        # Verify OOXML Native Zotero Field Injection
        out_target = "/home/vd00026/Desktop/Zotero_Link/ACTA2_Manuscript_test_linked.docx"
        link_docx_manuscript(doc_path, sites, refs, output_target=out_target)
        self.assertTrue(os.path.exists(out_target))

        out_doc = docx.Document(out_target)
        xml_all = "".join([p._p.xml for p in out_doc.paragraphs])
        self.assertIn("ADDIN ZOTERO_ITEM", xml_all)
        self.assertIn("ADDIN ZOTERO_BIBL", xml_all)
        self.assertIn("ADDIN ZOTERO_PREF_1", xml_all)

        orig_doc = docx.Document(doc_path)
        self.assertEqual(len(out_doc.tables), len(orig_doc.tables), "All 11 tables must be preserved")
        self.assertEqual(len(out_doc.paragraphs), len(orig_doc.paragraphs), "All 176 paragraphs must be preserved")

    def test_09_bot_verification_and_handle_discrimination(self):
        # 1. Test bot-protected real DOI (e.g. Oxford Academic / Brain 10.1093/brain/aws172)
        ref_bot = ReferenceEntry(
            ref_num=1,
            raw_text="1. Author. Brain paper. 2012. doi: 10.1093/brain/aws172",
            doi="10.1093/brain/aws172"
        )
        verdict_bot = validate_single_reference(ref_bot)
        self.assertIn(verdict_bot.status, ["bot_protected", "verified"])
        self.assertTrue(verdict_bot.is_reachable)
        self.assertNotEqual(verdict_bot.status, "unreachable", "Bot-protected DOI must not be classified as unreachable")

        # 2. Test completely fake unresolvable DOI
        ref_fake = ReferenceEntry(
            ref_num=2,
            raw_text="2. Fake Author. Nonexistent Paper. 2024. doi: 10.1016/fake.broken.doi.99999",
            doi="10.1016/fake.broken.doi.99999"
        )
        verdict_fake = validate_single_reference(ref_fake)
        self.assertEqual(verdict_fake.status, "unreachable", "Nonexistent DOI must be classified as unreachable")
        self.assertFalse(verdict_fake.is_reachable)

    def test_10_clinical_scale_and_score_rejection(self):
        from server.parser import parse_paragraphs_list

        user_clinical_doc = [
            "INTRODUCTION",
            "(modified Thrombolysis in Cerebral Infarction 2b-3), a core (relative cerebral blood flow <30%) less than 25 mL, mismatch ratio at least 1.8, and mismatch volume at least 15 mL. Admission NWU was measured on noncontrast CT with CT perfusion as the spatial reference; venous outflow was graded on CT angiography (0-8).",
            "Functional outcome was evaluated with the modified Rankin Scale (0-6) and ASPECTS score (0-10). Neurological deficit on arrival was measured using GCS (3-15).",
            "Prior surgical reports confirmed significant clinical benefit (1, 2). Subsequent multicenter trials confirmed these findings (3-5).",
            "REFERENCES",
            "1. First Author. Article 1. 2020. doi: 10.1038/s41586-020-2649-2",
            "2. Second Author. Article 2. 2021. doi: 10.1056/NEJMoa2002032",
            "3. Third Author. Article 3. 2022. doi: 10.1038/nature12373",
            "4. Fourth Author. Article 4. 2023. doi: 10.1038/nature12374",
            "5. Fifth Author. Article 5. 2024. doi: 10.1038/nature12375",
            "6. Sixth Author. Article 6. 2024. doi: 10.1038/nature12376",
            "7. Seventh Author. Article 7. 2024. doi: 10.1038/nature12377",
            "8. Eighth Author. Article 8. 2024. doi: 10.1038/nature12378",
            "9. Ninth Author. Article 9. 2024. doi: 10.1038/nature12379",
            "10. Tenth Author. Article 10. 2024. doi: 10.1038/nature12380"
        ]

        # Test both auto and paren modes
        for mode in ["auto", "paren"]:
            paras, sites, refs = parse_paragraphs_list(user_clinical_doc, citation_format=mode)
            detected_texts = [s.text for s in sites]
            
            # Assert all clinical scales are REJECTED
            self.assertNotIn("(0-8)", detected_texts, f"Mode {mode}: (0-8) must NOT be detected as citation")
            self.assertNotIn("(0-6)", detected_texts, f"Mode {mode}: (0-6) must NOT be detected as citation")
            self.assertNotIn("(0-10)", detected_texts, f"Mode {mode}: (0-10) must NOT be detected as citation")
            self.assertNotIn("(3-15)", detected_texts, f"Mode {mode}: GCS (3-15) must NOT be detected as citation")
            
            # Assert genuine citations are correctly DETECTED
            self.assertIn("(1, 2)", detected_texts, f"Mode {mode}: (1, 2) MUST be detected as valid citation")
            self.assertIn("(3-5)", detected_texts, f"Mode {mode}: (3-5) MUST be detected as valid citation")
            
            # Verify total sites
            self.assertEqual(len(sites), 2, f"Mode {mode}: Exactly 2 citations should be found")

    def test_11_clinical_abbreviations_and_percentages(self):
        from server.parser import parse_paragraphs_list

        doc_with_stats = [
            "INTRODUCTION",
            "In patients with severe stenosis (>70%), treatment with stenting reduced stroke risk (OR 1.45, 95% CI 1.12-1.89; P < .001).",
            "The trial enrolled a cohort (n = 120) receiving antiplatelet therapy (75 mg/day). Average hospital stay was (mean 4.2 ± 1.1 days).",
            "Previous investigators observed similar treatment response (1).",
            "REFERENCES",
            "1. Clinical Investigator. Randomized Stroke Trial. 2023. doi: 10.1056/NEJMoa2002032"
        ]

        paras, sites, refs = parse_paragraphs_list(doc_with_stats, citation_format="auto")
        detected_texts = [s.text for s in sites]
        
        # Verify statistics and cohort abbreviations are NOT matched
        self.assertNotIn("(>70%)", detected_texts)
        self.assertNotIn("(OR 1.45, 95% CI 1.12-1.89; P < .001)", detected_texts)
        self.assertNotIn("(n = 120)", detected_texts)
        self.assertNotIn("(75 mg/day)", detected_texts)
        self.assertNotIn("(mean 4.2 ± 1.1 days)", detected_texts)
        
        # Only true citation (1) should be found
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].text, "(1)")
        self.assertEqual(sites[0].nums, [1])

    def test_12_consecutive_order_detection(self):
        from server.parser import parse_paragraphs_list
        from server.validator import map_usage_and_sequence

        # Create out-of-order manuscript: cites [3] first, then [1], then [2]
        out_of_order_doc = [
            "INTRODUCTION",
            "Initial observation was made by Third Author (3).",
            "Subsequently First Author confirmed this finding (1).",
            "Finally Second Author published the consensus (2).",
            "REFERENCES",
            "1. First Author. 2020. doi: 10.1038/s41586-020-2649-2",
            "2. Second Author. 2021. doi: 10.1056/NEJMoa2002032",
            "3. Third Author. 2022. doi: 10.1038/nature12373"
        ]

        paras, sites, refs = parse_paragraphs_list(out_of_order_doc, citation_format="paren")
        ref_map, seq_valid, warnings = map_usage_and_sequence(refs, sites)

        self.assertFalse(seq_valid, "Non-consecutive citation order must be flagged as invalid")
        self.assertGreaterEqual(len(warnings), 1, "Must generate sequence warning when [3] is cited before [1]")
        self.assertIn("Reference [3] was cited before Reference [1]", warnings[0])

    def test_13_ris_metadata_completeness(self):
        doc_path = "/home/vd00026/Desktop/Zotero_Link/ACTA2_Manuscript_11.14.2026.docx"
        if not os.path.exists(doc_path):
            self.skipTest("ACTA2 manuscript not present")

        paras, sites, refs = parse_docx_manuscript(doc_path)
        ris = generate_ris(refs)

        # Check required standard RIS tags
        self.assertIn("TY  - JOUR", ris)
        self.assertIn("TI  -", ris)
        self.assertIn("AU  -", ris)
        self.assertIn("DO  -", ris)
        self.assertIn("ER  -", ris)
        self.assertEqual(ris.count("ER  -"), 43, "Must have exactly 43 ER tags for 43 references")

    def test_14_docx_native_fields_xml_integrity(self):
        doc_path = "/home/vd00026/Desktop/Zotero_Link/ACTA2_Manuscript_11.14.2026.docx"
        if not os.path.exists(doc_path):
            self.skipTest("ACTA2 manuscript not present")

        paras, sites, refs = parse_docx_manuscript(doc_path)
        out_target = "/home/vd00026/Desktop/Zotero_Link/ACTA2_Manuscript_integrity_check.docx"
        link_docx_manuscript(doc_path, sites, refs, output_target=out_target)

        # Open linked document and verify full XML structure
        linked_doc = docx.Document(out_target)
        self.assertEqual(len(linked_doc.paragraphs), len(paras))
        self.assertEqual(len(linked_doc.tables), 11)

        # Verify tables content is not corrupted
        first_table = linked_doc.tables[0]
        self.assertGreater(len(first_table.rows), 0)

        # Clean up test artifact
        if os.path.exists(out_target):
            os.remove(out_target)

    def test_15_empty_and_corrupt_files(self):
        from server.parser import parse_paragraphs_list

        # Empty document
        empty_paras, empty_sites, empty_refs = parse_paragraphs_list([], citation_format="auto")
        self.assertEqual(len(empty_paras), 0)
        self.assertEqual(len(empty_sites), 0)
        self.assertEqual(len(empty_refs), 0)

        # Document with no references section
        no_ref_paras = ["This is just a paper with no bibliography.", "Some text here."]
        paras, sites, refs = parse_paragraphs_list(no_ref_paras, citation_format="auto")
        self.assertEqual(len(refs), 0)
        self.assertEqual(len(sites), 0)

    def test_16_missing_doi_automatic_recovery(self):
        # 1. Reference without DOI that exists in Crossref
        ref_no_doi = ReferenceEntry(
            ref_num=1,
            raw_text="1. Milewicz DM, Østergaard JR, Ala-Kokko L. De novo ACTA2 mutation causes a novel syndrome of multisystemic smooth muscle dysfunction. Am J Med Genet A. 2010;152A(10):2437-2443.",
            title="De novo ACTA2 mutation causes a novel syndrome of multisystemic smooth muscle dysfunction",
            authors=["Milewicz DM", "Østergaard JR", "Ala-Kokko L"],
            doi=""
        )
        verdict = validate_single_reference(ref_no_doi)
        self.assertTrue(verdict.is_recovered_doi, "Should automatically recover missing DOI")
        self.assertEqual(verdict.recovered_doi.lower(), "10.1002/ajmg.a.33657")
        self.assertTrue(verdict.is_reachable)

        # 2. Non-indexed report without DOI (should NOT hallucinate)
        ref_unindexed = ReferenceEntry(
            ref_num=2,
            raw_text="2. Hospital Committee. Clinical Internal Guideline 2024 for Local Floor Treatment.",
            title="Clinical Internal Guideline 2024 for Local Floor Treatment",
            doi=""
        )
        verdict_unidx = validate_single_reference(ref_unindexed)
        self.assertFalse(verdict_unidx.is_recovered_doi, "Should not hallucinate DOI for local guidelines")
        self.assertEqual(verdict_unidx.status, "missing_doi")

    def test_17_format_profiler_and_parenthetical_immunity(self):
        from server.parser import parse_docx_manuscript
        doc_path = "/home/vd00026/Desktop/Zotero_Link/ACTA2_Manuscript_11.14.2026.docx"
        if not os.path.exists(doc_path):
            self.skipTest("ACTA2 manuscript not present")

        # In Auto mode, ACTA2 manuscript should profile as 'sup'
        paras, sites, refs = parse_docx_manuscript(doc_path, citation_format="auto")
        
        # Verify 100% of detected sites are superscripts
        self.assertTrue(all(s.kind == "sup" for s in sites), "All detected sites in ACTA2 must be superscripts")
        
        # Verify no parenthetical clinical scales or measurements were matched
        detected_texts = [s.text for s in sites]
        self.assertNotIn("(0-8)", detected_texts)
        self.assertNotIn("(2b-3)", detected_texts)
        self.assertNotIn("(1.8)", detected_texts)
        self.assertNotIn("(<30%)", detected_texts)

    def test_18_multiline_reference_stitching(self):
        from server.parser import parse_paragraphs_list

        doc_with_wrapped_doi = [
            "INTRODUCTION",
            "This study investigates cavernous malformations [1].",
            "REFERENCES",
            "1. Al-Shahi Salman R, Hall JM, Horne MA, et al. Untreated clinical course of cerebral cavernous malformations: a prospective, population-based cohort study. Lancet Neurol. 2012;11(3):217-224.",
            "doi: 10.1016/S1474-4422(12)70004-2",
            "2. Second Author. Second Title. Journal. 2021;10:1-5.",
            "https://doi.org/10.1038/s41586-020-2649-2"
        ]

        paras, sites, refs = parse_paragraphs_list(doc_with_wrapped_doi, citation_format="bracket")
        self.assertEqual(len(refs), 2, "Should have 2 references")
        
        # Verify both wrapped DOIs were stitched into their respective references
        self.assertEqual(refs[0].ref_num, 1)
        self.assertEqual(refs[0].doi, "10.1016/S1474-4422(12)70004-2")
        self.assertIn("doi: 10.1016/S1474-4422(12)70004-2", refs[0].raw_text)

        self.assertEqual(refs[1].ref_num, 2)
        self.assertEqual(refs[1].doi, "10.1038/s41586-020-2649-2")

    def test_19_section_heading_and_figure_legend_rejection(self):
        from server.parser import parse_paragraphs_list

        doc_with_headings_and_appendix = [
            "1. Introduction",
            "Cerebral cavernous malformations are common vascular lesions [1].",
            "2. Methods",
            "Patients were imaged with 3T MRI.",
            "REFERENCES",
            "1. Al-Shahi Salman R, et al. Untreated clinical course. Lancet Neurol. 2012. doi: 10.1016/S1474-4422(12)70004-2",
            "Supplementary Material",
            "1. Supplementary Table 1. Patient cohort demographics.",
            "2. Supplementary Figure 1. Flowchart of study inclusion."
        ]

        paras, sites, refs = parse_paragraphs_list(doc_with_headings_and_appendix, citation_format="bracket")
        
        # Verify that '1. Introduction' and '2. Methods' are NOT parsed as references
        # And '1. Supplementary Table 1' after 'Supplementary Material' is NOT parsed as reference
        self.assertEqual(len(refs), 1, "Only the genuine reference should be parsed")
        self.assertEqual(refs[0].ref_num, 1)
        self.assertIn("Al-Shahi Salman", refs[0].raw_text)

    def test_20_multi_registry_doi_recovery_europepmc_openalex(self):
        from server.validator import search_europepmc_bibliographic, search_openalex_bibliographic
        
        # 1. Test Europe PMC discovery
        title_ep = "Untreated clinical course of cerebral cavernous malformations: a prospective, population-based cohort study"
        doi_ep, meta_ep = search_europepmc_bibliographic("", title_ep)
        self.assertTrue(bool(doi_ep), "Europe PMC should find Lancet Neurol paper DOI")
        self.assertEqual(doi_ep.lower(), "10.1016/s1474-4422(12)70004-2")

        # 2. Test OpenAlex discovery
        title_oa = "Brain arteriovenous malformations"
        doi_oa, meta_oa = search_openalex_bibliographic("", title_oa)
        self.assertTrue(bool(doi_oa), "OpenAlex should find Brain arteriovenous malformations paper")
        self.assertIn("10.1038/nrdp.2015.8", doi_oa.lower())

    def test_21_ama_sequential_renumbering_and_reordering(self):
        from io import BytesIO
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript
        from server.ris_generator import generate_ris

        # Create a real docx with out-of-order citations: [3] first, [1] second, [2] third
        doc = docx.Document()
        doc.add_paragraph("INTRODUCTION")
        doc.add_paragraph("Third Author made the breakthrough finding [3].")
        doc.add_paragraph("Subsequently First Author published the initial cohort [1].")
        doc.add_paragraph("Finally Second Author drafted the consensus statement [2].")
        doc.add_paragraph("REFERENCES")
        doc.add_paragraph("1. First Author. Article One. 2021. doi: 10.1038/s41586-020-2649-2")
        doc.add_paragraph("2. Second Author. Article Two. 2022. doi: 10.1056/NEJMoa2002032")
        doc.add_paragraph("3. Third Author. Article Three. 2023. doi: 10.1038/nature12373")

        in_stream = BytesIO()
        doc.save(in_stream)
        in_stream.seek(0)

        # Parse document
        paras, sites, refs = parse_docx_manuscript(in_stream, citation_format="bracket")
        self.assertEqual(len(refs), 3)
        self.assertEqual(len(sites), 3)

        # Link and renumber according to AMA style
        in_stream.seek(0)
        out_stream = BytesIO()
        link_docx_manuscript(in_stream, sites, refs, output_target=out_stream, renumber_ama=True)
        out_stream.seek(0)

        # Verify output docx
        out_doc = docx.Document(out_stream)
        out_paras = [p.text.strip() for p in out_doc.paragraphs if p.text.strip()]

        # Find bibliography paragraphs in output
        ref_lines = [p for p in out_paras if re.match(r'^\d{1,3}\.\s', p)]
        self.assertEqual(len(ref_lines), 3, "Must have exactly 3 bibliography entries")

        # Ref 1 must be Third Author (cited first!)
        self.assertTrue(ref_lines[0].startswith("1. Third Author"), f"First ref must be Third Author, got: {ref_lines[0]}")
        # Ref 2 must be First Author (cited second!)
        self.assertTrue(ref_lines[1].startswith("2. First Author"), f"Second ref must be First Author, got: {ref_lines[1]}")
        # Ref 3 must be Second Author (cited third!)
        self.assertTrue(ref_lines[2].startswith("3. Second Author"), f"Third ref must be Second Author, got: {ref_lines[2]}")

        # Check in-text citations: must be 1, 2, 3 in order
        in_text_paras = [p.text for p in out_doc.paragraphs[:5]]
        self.assertIn("Third Author made the breakthrough finding", in_text_paras[1])
        self.assertTrue(in_text_paras[1].endswith(".1") or in_text_paras[1].endswith(" 1"))
        self.assertIn("Subsequently First Author published the initial cohort", in_text_paras[2])
        self.assertTrue(in_text_paras[2].endswith(".2") or in_text_paras[2].endswith(" 2"))
        self.assertIn("Finally Second Author drafted the consensus statement", in_text_paras[3])
        self.assertTrue(in_text_paras[3].endswith(".3") or in_text_paras[3].endswith(" 3"))

    def test_22_ama_range_condensation(self):
        from server.linker import format_condensed_citation
        self.assertEqual(format_condensed_citation([1]), "1")
        self.assertEqual(format_condensed_citation([1, 2]), "1,2")
        self.assertEqual(format_condensed_citation([1, 2, 3]), "1-3")
        self.assertEqual(format_condensed_citation([3, 1, 2]), "1-3")
        self.assertEqual(format_condensed_citation([1, 2, 3, 5]), "1-3,5")
        self.assertEqual(format_condensed_citation([1, 3, 4, 5, 7, 8, 9]), "1,3-5,7-9")

    def test_23_uncited_reference_placed_at_end(self):
        from io import BytesIO
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript, build_ama_renumbering_map

        # Manuscript where ref 2 is never cited (only 1 and 3 are cited)
        doc = docx.Document()
        doc.add_paragraph("INTRODUCTION")
        doc.add_paragraph("First Author reported the original discovery [1].")
        doc.add_paragraph("Third Author confirmed the clinical trial [3].")
        doc.add_paragraph("REFERENCES")
        doc.add_paragraph("1. First Author. 2021.")
        doc.add_paragraph("2. Uncited Author. 2022.")
        doc.add_paragraph("3. Third Author. 2023.")

        in_stream = BytesIO()
        doc.save(in_stream)
        in_stream.seek(0)

        paras, sites, refs = parse_docx_manuscript(in_stream, citation_format="bracket")
        mapping, first_seen, uncited = build_ama_renumbering_map(refs, sites)

        # Ref 1 -> 1
        # Ref 3 -> 2
        # Ref 2 (uncited) -> 3 (appended at end)
        self.assertEqual(mapping[1], 1)
        self.assertEqual(mapping[3], 2)
        self.assertEqual(mapping[2], 3)
        self.assertEqual(uncited, [2])

        # Link and check bibliography re-ordering
        in_stream.seek(0)
        out_stream = BytesIO()
        link_docx_manuscript(in_stream, sites, refs, output_target=out_stream, renumber_ama=True)
        out_stream.seek(0)

        out_doc = docx.Document(out_stream)
        ref_lines = [p.text.strip() for p in out_doc.paragraphs if re.match(r'^\d{1,3}\.\s', p.text.strip())]
        self.assertEqual(len(ref_lines), 3)
        self.assertTrue(ref_lines[0].startswith("1. First Author"))
        self.assertTrue(ref_lines[1].startswith("2. Third Author"))
        self.assertTrue(ref_lines[2].startswith("3. Uncited Author"))

    def test_24_acta2_identity_permutation(self):
        from server.parser import parse_docx_manuscript
        from server.linker import build_ama_renumbering_map
        doc_path = "/home/vd00026/Desktop/Zotero_Link/ACTA2_Manuscript_11.14.2026.docx"
        if not os.path.exists(doc_path):
            self.skipTest("ACTA2 manuscript not present")
        paras, sites, refs = parse_docx_manuscript(doc_path, citation_format="auto")
        mapping, first_seen, uncited = build_ama_renumbering_map(refs, sites)
        self.assertEqual(len(uncited), 0, "All 43 references are cited in ACTA2")
        # Every reference number maps to itself: mapping[n] == n for all n
        for n in range(1, 44):
            self.assertEqual(mapping[n], n, f"Reference {n} must map to itself in ACTA2")

    def test_25_track_changes_in_text_citations(self):
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript
        from docx.oxml.ns import qn

        doc = docx.Document()
        doc.add_paragraph("Early breakthrough was discovered by pioneer [3].")
        doc.add_paragraph("Later confirmed by [1].")
        doc.add_paragraph("References")
        doc.add_paragraph("1. Alpha A. First paper. J Mol Biol. 2010;10:1-5.")
        doc.add_paragraph("2. Beta B. Second paper. J Cell Sci. 2011;11:2-6.")
        doc.add_paragraph("3. Gamma C. Third paper. Nature. 2012;12:3-7.")

        in_stream = BytesIO()
        doc.save(in_stream)
        in_stream.seek(0)

        paras, sites, refs = parse_docx_manuscript(in_stream, citation_format="bracket")
        in_stream.seek(0)
        out_stream = BytesIO()
        link_docx_manuscript(
            in_stream, sites, refs,
            output_target=out_stream,
            renumber_ama=True,
            track_changes=True,
            author="Co-Scientist"
        )
        out_stream.seek(0)

        out_doc = docx.Document(out_stream)
        p0 = out_doc.paragraphs[0]
        # Inspect p0 XML for w:del and w:ins
        del_els = p0._p.findall(qn('w:del'))
        ins_els = p0._p.findall(qn('w:ins'))
        self.assertGreaterEqual(len(del_els), 1, "Must contain <w:del> for old citation [3]")
        self.assertGreaterEqual(len(ins_els), 1, "Must contain <w:ins> for new citation 1")

        # Verify author attribute
        self.assertEqual(del_els[0].get(qn('w:author')), "Co-Scientist")
        self.assertEqual(ins_els[0].get(qn('w:author')), "Co-Scientist")

        # Verify delText contains '[3]'
        del_text_el = del_els[0].find(f".//{qn('w:delText')}")
        self.assertIsNotNone(del_text_el)
        self.assertEqual(del_text_el.text, "[3]")

        # Verify ins text contains '1' with superscript formatting
        ins_text_el = ins_els[0].find(f".//{qn('w:t')}")
        self.assertIsNotNone(ins_text_el)
        self.assertEqual(ins_text_el.text, "1")
        rPr = ins_els[0].find(f".//{qn('w:rPr')}")
        self.assertIsNotNone(rPr)
        va = rPr.find(qn('w:vertAlign'))
        self.assertIsNotNone(va)
        self.assertEqual(va.get(qn('w:val')), "superscript")

    def test_26_track_changes_in_bibliography_and_doi(self):
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript
        from server.models import ValidationVerdict
        from docx.oxml.ns import qn

        doc = docx.Document()
        doc.add_paragraph("Early breakthrough pioneer [3].")
        doc.add_paragraph("References")
        doc.add_paragraph("1. Alpha A. First paper. J Mol Biol. 2010.")
        doc.add_paragraph("2. Beta B. Second paper. J Cell Sci. 2011.")
        doc.add_paragraph("3. Gamma C. Third paper. Nature. 2012.")

        in_stream = BytesIO()
        doc.save(in_stream)
        in_stream.seek(0)

        paras, sites, refs = parse_docx_manuscript(in_stream, citation_format="bracket")
        verdicts = {
            3: ValidationVerdict(
                ref_num=3, is_reachable=True, is_recovered_doi=True,
                http_status=200, resolved_url="https://doi.org/10.1000/recovered3",
                recovered_doi="10.1000/recovered3", status="recovered"
            )
        }

        in_stream.seek(0)
        out_stream = BytesIO()
        link_docx_manuscript(
            in_stream, sites, refs,
            verdicts=verdicts,
            output_target=out_stream,
            renumber_ama=True,
            track_changes=True,
            author="Co-Scientist"
        )
        out_stream.seek(0)

        out_doc = docx.Document(out_stream)
        # Bibliography starts after paragraph 1
        bib_paras = [p for p in out_doc.paragraphs if "Gamma C" in p.text]
        self.assertEqual(len(bib_paras), 1)
        gamma_p = bib_paras[0]

        # Verify tracked deletion of old prefix '3.'
        del_els = gamma_p._p.findall(qn('w:del'))
        self.assertGreaterEqual(len(del_els), 1)
        del_prefix = del_els[0].find(f".//{qn('w:delText')}")
        self.assertIsNotNone(del_prefix)
        self.assertEqual(del_prefix.text, "3.")

        # Verify tracked insertion of new prefix '1.'
        ins_els = gamma_p._p.findall(qn('w:ins'))
        self.assertGreaterEqual(len(ins_els), 2, "Must contain prefix ins and recovered DOI ins")
        ins_prefix = ins_els[0].find(f".//{qn('w:t')}")
        self.assertIsNotNone(ins_prefix)
        self.assertEqual(ins_prefix.text, "1.")

        # Verify tracked insertion of recovered DOI
        ins_doi = ins_els[1].find(f".//{qn('w:t')}")
        self.assertIsNotNone(ins_doi)
        self.assertIn("10.1000/recovered3", ins_doi.text)

    def test_27_track_revisions_setting_flag(self):
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript
        from docx.oxml.ns import qn

        doc = docx.Document()
        doc.add_paragraph("Early text [1].")
        doc.add_paragraph("References")
        doc.add_paragraph("1. Alpha A. Paper. 2010.")

        in_stream = BytesIO()
        doc.save(in_stream)

        in_stream.seek(0)
        paras, sites, refs = parse_docx_manuscript(in_stream, citation_format="bracket")

        # Tracked mode -> must set trackRevisions
        in_stream.seek(0)
        out_tracked = BytesIO()
        link_docx_manuscript(in_stream, sites, refs, output_target=out_tracked, track_changes=True)
        out_tracked.seek(0)
        doc_tracked = docx.Document(out_tracked)
        self.assertIsNotNone(doc_tracked.settings._element.find(qn('w:trackRevisions')))

        # Clean mode -> must not set trackRevisions
        in_stream.seek(0)
        out_clean = BytesIO()
        link_docx_manuscript(in_stream, sites, refs, output_target=out_clean, track_changes=False)
        out_clean.seek(0)
        doc_clean = docx.Document(out_clean)
        self.assertIsNone(doc_clean.settings._element.find(qn('w:trackRevisions')))

    def test_28_clean_vs_tracked_parity(self):
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript
        from docx.oxml.ns import qn

        doc_path = "/home/vd00026/Desktop/Zotero_Link/ACTA2_Manuscript_11.14.2026.docx"
        if not os.path.exists(doc_path):
            self.skipTest("ACTA2 manuscript not present")

        paras, sites, refs = parse_docx_manuscript(doc_path, citation_format="auto")

        # Clean run
        out_clean = BytesIO()
        link_docx_manuscript(doc_path, sites, refs, output_target=out_clean, track_changes=False)
        out_clean.seek(0)
        doc_clean = docx.Document(out_clean)
        clean_dels = sum(len(p._p.findall(qn('w:del'))) for p in doc_clean.paragraphs)
        self.assertEqual(clean_dels, 0, "Clean manuscript must have 0 deletions")

        # Tracked run
        out_tracked = BytesIO()
        link_docx_manuscript(doc_path, sites, refs, output_target=out_tracked, track_changes=True)
        out_tracked.seek(0)
        doc_tracked = docx.Document(out_tracked)
        self.assertIsNotNone(doc_tracked.settings._element.find(qn('w:trackRevisions')))
        self.assertEqual(len(doc_clean.paragraphs), len(doc_tracked.paragraphs))

    def test_29_reference_section_bounds_isolation(self):
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript

        doc = docx.Document()
        doc.add_paragraph("METHODS")
        doc.add_paragraph("1. Inclusion criteria: confirmed diagnosis.")
        doc.add_paragraph("2. Exclusion criteria: secondary etiology.")
        doc.add_paragraph("RESULTS")
        doc.add_paragraph("Pioneer study demonstrated clinical benefit [2]. Later verified [1].")
        doc.add_paragraph("REFERENCES")
        doc.add_paragraph("1. Alpha A. First paper. Lancet. 2010.")
        doc.add_paragraph("2. Beta B. Second paper. Nature. 2012.")
        doc.add_paragraph("SUPPLEMENTARY MATERIAL")
        doc.add_paragraph("1. Supplementary Table 1. Demographics.")

        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)

        paras, sites, refs = parse_docx_manuscript(buf, citation_format="bracket")
        buf.seek(0)

        out_buf = BytesIO()
        link_docx_manuscript(buf, sites, refs, output_target=out_buf, track_changes=True, renumber_ama=True)
        out_buf.seek(0)

        out_doc = docx.Document(out_buf)
        # Methods numbered lists must be completely untouched and remain at paragraphs 1 and 2
        self.assertTrue(out_doc.paragraphs[1].text.strip().startswith("1. Inclusion criteria"))
        self.assertTrue(out_doc.paragraphs[2].text.strip().startswith("2. Exclusion criteria"))

        # References must be reordered: Beta B (cited first) comes before Alpha A
        ref_header_idx = [i for i, p in enumerate(out_doc.paragraphs) if p.text.strip() == "REFERENCES"][0]
        self.assertIn("Beta B", out_doc.paragraphs[ref_header_idx + 1].text)
        self.assertIn("Alpha A", out_doc.paragraphs[ref_header_idx + 2].text)

        # Supplementary materials must be untouched
        self.assertTrue(out_doc.paragraphs[ref_header_idx + 4].text.strip().startswith("1. Supplementary Table 1"))

    def test_30_atomic_multiline_reference_preservation(self):
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript

        doc = docx.Document()
        doc.add_paragraph("Early text cites [2].")
        doc.add_paragraph("REFERENCES")
        doc.add_paragraph("1. First Author. First Article. Journal. 2010.")
        doc.add_paragraph("2. Second Author. Second Article. Journal. 2015.")
        doc.add_paragraph("   doi: 10.1016/j.cell.2015.01.001 (continuation line)")

        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)

        paras, sites, refs = parse_docx_manuscript(buf, citation_format="bracket")
        buf.seek(0)

        out_buf = BytesIO()
        link_docx_manuscript(buf, sites, refs, output_target=out_buf, track_changes=True, renumber_ama=True)
        out_buf.seek(0)

        out_doc = docx.Document(out_buf)
        ref_header_idx = [i for i, p in enumerate(out_doc.paragraphs) if p.text.strip() == "REFERENCES"][0]
        # Second Author was cited first, so it becomes reference #1
        self.assertIn("Second Author", out_doc.paragraphs[ref_header_idx + 1].text)
        # Continuation line must remain immediately following Second Author!
        self.assertIn("continuation line", out_doc.paragraphs[ref_header_idx + 2].text)
        # First Author is now reference #2
        self.assertIn("First Author", out_doc.paragraphs[ref_header_idx + 3].text)

    def test_31_schema_pPr_first_invariant(self):
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript
        from docx.oxml.ns import qn

        doc_path = "/home/vd00026/Desktop/Zotero_Link/ACTA2_Manuscript_11.14.2026.docx"
        if not os.path.exists(doc_path):
            self.skipTest("ACTA2 manuscript not present")

        paras, sites, refs = parse_docx_manuscript(doc_path, citation_format="auto")
        out_buf = BytesIO()
        link_docx_manuscript(doc_path, sites, refs, output_target=out_buf, track_changes=True, renumber_ama=True)
        out_buf.seek(0)

        out_doc = docx.Document(out_buf)
        # Verify that for every single paragraph in the output document:
        # If w:pPr exists, it is strictly the first child of w:p
        for i, p in enumerate(out_doc.paragraphs):
            pPr = p._p.find(qn('w:pPr'))
            if pPr is not None:
                self.assertEqual(
                    p._p[0].tag, qn('w:pPr'),
                    f"Paragraph {i} violates OpenXML schema: w:pPr is not the first child"
                )

    def test_32_document_with_existing_tracked_insertions(self):
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript
        from lxml import etree
        from docx.oxml.ns import qn

        doc = docx.Document()
        p = doc.add_paragraph("Base text ")
        # Insert a run with citation inside w:ins from a prior reviewer
        ins = etree.SubElement(p._p, qn('w:ins'), {qn('w:id'): '1', qn('w:author'): 'Dr. Reviewer'})
        r_ins = etree.SubElement(ins, qn('w:r'))
        etree.SubElement(r_ins, qn('w:t')).text = "with inserted citation [1]"
        p.add_run(" end of paragraph.")

        doc.add_paragraph("REFERENCES")
        doc.add_paragraph("1. Alpha A. Active study. Lancet 2020.")

        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)

        paras, sites, refs = parse_docx_manuscript(buf, citation_format="bracket")
        self.assertEqual(len(refs), 1)
        self.assertEqual(len(sites), 1, "Must detect citation inside pre-existing <w:ins>")
        self.assertEqual(sites[0].nums, [1])

        # Link document
        buf.seek(0)
        out_buf = BytesIO()
        link_docx_manuscript(buf, sites, refs, output_target=out_buf, track_changes=True)
        out_buf.seek(0)
        out_doc = docx.Document(out_buf)
        self.assertIn("Alpha A", out_doc.paragraphs[2].text)

    def test_33_document_with_existing_tracked_deletions(self):
        from server.parser import parse_docx_manuscript
        from lxml import etree
        from docx.oxml.ns import qn

        doc = docx.Document()
        p = doc.add_paragraph("Base text ")
        # Add a deleted citation inside w:del
        del_el = etree.SubElement(p._p, qn('w:del'), {qn('w:id'): '2', qn('w:author'): 'Dr. Reviewer'})
        r_del = etree.SubElement(del_el, qn('w:r'))
        etree.SubElement(r_del, qn('w:delText')).text = "deleted citation [99]"
        p.add_run(" continuing active sentence.")

        doc.add_paragraph("REFERENCES")
        doc.add_paragraph("1. Alpha A. Active study. Lancet 2020.")

        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)

        paras, sites, refs = parse_docx_manuscript(buf, citation_format="bracket")
        # The deleted citation [99] must NOT be detected as an active site!
        self.assertEqual(len(sites), 0, "Deleted citations in <w:del> must be completely ignored")

    def test_34_accept_prior_revisions_baseline(self):
        from server.parser import has_tracked_revisions, accept_prior_revisions
        from lxml import etree
        from docx.oxml.ns import qn

        doc = docx.Document()
        p = doc.add_paragraph("Original ")
        del_el = etree.SubElement(p._p, qn('w:del'), {qn('w:id'): '1', qn('w:author'): 'Reviewer'})
        r_del = etree.SubElement(del_el, qn('w:r'))
        etree.SubElement(r_del, qn('w:delText')).text = "old words "

        ins_el = etree.SubElement(p._p, qn('w:ins'), {qn('w:id'): '2', qn('w:author'): 'Reviewer'})
        r_ins = etree.SubElement(ins_el, qn('w:r'))
        etree.SubElement(r_ins, qn('w:t')).text = "new words "
        p.add_run("finished.")

        self.assertTrue(has_tracked_revisions(doc))
        resolved_count = accept_prior_revisions(doc)
        self.assertEqual(resolved_count, 2)
        self.assertFalse(has_tracked_revisions(doc))
        self.assertEqual(p.text, "Original new words finished.")
        # Ensure no nested revisions or lingering del elements exist
        self.assertEqual(len(doc._body._element.xpath('.//w:del')), 0)
        self.assertEqual(len(doc._body._element.xpath('.//w:ins')), 0)

    def test_35_guarded_job_state_machine(self):
        from server.models import JobStatus, JobRecord

        job = JobRecord(job_id="test-job-123", status=JobStatus.INITIALIZED, filename="test.docx")
        self.assertEqual(job.status, JobStatus.INITIALIZED)

        # Illegal jump directly to READY
        with self.assertRaises(ValueError):
            job.transition_to(JobStatus.READY)

        # Legal progression
        job.transition_to(JobStatus.PARSING)
        self.assertEqual(job.status, JobStatus.PARSING)

        job.transition_to(JobStatus.AUDITED)
        self.assertEqual(job.status, JobStatus.AUDITED)

        # Cannot jump back to PARSING from AUDITED
        with self.assertRaises(ValueError):
            job.transition_to(JobStatus.PARSING)

        job.transition_to(JobStatus.LINKING)
        self.assertEqual(job.status, JobStatus.LINKING)

        job.transition_to(JobStatus.READY)
        self.assertEqual(job.status, JobStatus.READY)

    def test_36_preserve_existing_tracked_changes_without_accepting(self):
        """Verifies that pre-existing tracked changes are preserved and new revisions are added on top."""
        doc = docx.Document()
        p = doc.add_paragraph("Background statement. ")
        # Reviewer 1 inserted text
        ins = etree.SubElement(p._p, qn('w:ins'), {qn('w:id'): '10', qn('w:author'): 'Reviewer 1'})
        r_ins = etree.SubElement(ins, qn('w:r'))
        etree.SubElement(r_ins, qn('w:t')).text = "Reviewer added clause."
        
        # Reviewer 1 deleted text
        del_el = etree.SubElement(p._p, qn('w:del'), {qn('w:id'): '11', qn('w:author'): 'Reviewer 1'})
        r_del = etree.SubElement(del_el, qn('w:r'))
        etree.SubElement(r_del, qn('w:delText')).text = "Obsolete clause."

        p.add_run(" Final sentence with citation (1).")

        doc.add_paragraph("REFERENCES")
        doc.add_paragraph("1. Alpha A. Original Finding. Lancet 2020.")

        buf = BytesIO()
        doc.save(buf)
        buf.seek(0)

        # Parse without accepting revisions
        paras, sites, refs = parse_docx_manuscript(buf, citation_format="paren", accept_revisions=False)
        self.assertEqual(len(refs), 1)
        self.assertEqual(len(sites), 1)

        # Link document with track_changes=True (author='Co-Scientist')
        buf.seek(0)
        out_buf = BytesIO()
        link_docx_manuscript(buf, sites, refs, output_target=out_buf, track_changes=True, author="Co-Scientist")
        out_buf.seek(0)

        out_doc = docx.Document(out_buf)
        body = out_doc._body._element

        # Verify Reviewer 1 insertions and deletions are STILL IN THE DOCUMENT
        reviewer_inss = body.xpath('.//w:ins[@w:author="Reviewer 1"]')
        reviewer_dels = body.xpath('.//w:del[@w:author="Reviewer 1"]')
        self.assertGreaterEqual(len(reviewer_inss), 1, "Reviewer 1 insertion must not be accepted or removed")
        self.assertGreaterEqual(len(reviewer_dels), 1, "Reviewer 1 deletion must not be accepted or removed")

        # Verify Co-Scientist additions are layered on top
        co_inss = body.xpath('.//w:ins[@w:author="Co-Scientist"]')
        co_dels = body.xpath('.//w:del[@w:author="Co-Scientist"]')
        self.assertGreaterEqual(len(co_inss), 1, "Co-Scientist insertion must be present")
        self.assertGreaterEqual(len(co_dels), 1, "Co-Scientist deletion must be present")

    def test_37_clinical_patient_count_statement_rejection(self):
        """Verifies that numbered clinical patient count statements are never parsed as references."""
        lines = [
            "METHODS",
            "1. A total of 60 patients were enrolled between 2018 and 2022.",
            "2. Patients were aged 18 to 65 years in the 2020 cohort.",
            "3. Thirty-eight patients (63.3%) had initial presentation of ischemic stroke.",
            "4. Mean follow-up was 3.5 years in 2021.",
            "REFERENCES",
            "1. Smith J, Doe A. Treatment of Cerebrovascular Disease. Stroke 2021; 52: 100-105.",
            "2. Johnson K. Vascular Genetics. Nature 2022."
        ]
        paras, sites, refs = parse_paragraphs_list(lines, citation_format="paren")
        self.assertEqual(len(refs), 2, "Only authentic references must be captured")
        self.assertEqual(refs[0].authors, ["Smith J", "Doe A"])
        self.assertEqual(refs[1].title, "Vascular Genetics")

    def test_38_in_text_patient_count_paren_rejection(self):
        """Verifies that patient count and percentage parentheticals are never parsed as citations."""
        lines = [
            "INTRODUCTION",
            "The disease causes significant mortality (1).",
            "RESULTS",
            "In this study, 45 patients (12) were female and 33 were male.",
            "Initial presentation was ischemic stroke in 38 patients (38, 63.3%).",
            "Antithrombotic therapy was reported almost exclusively as antiplatelet (25; anticoagulation in 1).",
            "Demographics of the cohort (n = 60) showed high penetrance.",
            "REFERENCES",
            "1. Smith J. Cerebrovascular Disease. Lancet 2020."
        ]
        paras, sites, refs = parse_paragraphs_list(lines, citation_format="paren")
        self.assertEqual(len(refs), 1)
        self.assertEqual(len(sites), 1, "Only the real citation (1) in introduction should be captured")
        self.assertEqual(sites[0].sentence, "The disease causes significant mortality (1).")

    def test_39_in_text_age_and_year_range_rejection(self):
        """Verifies that age ranges, calendar year ranges, and duration intervals are rejected."""
        lines = [
            "INTRODUCTION",
            "Recent genomic guidelines recommend screening (1).",
            "METHODS",
            "Median age at index imaging was 7.0 years (3-14).",
            "Patients had a mean follow-up of 5 years (1-8).",
            "Duration of symptoms was 6 months (1-12).",
            "Data was collected over the entire study period (2018-2022).",
            "Evaluations performed in (2020) confirmed findings.",
            "REFERENCES",
            "1. Doe A. Clinical Guidelines. NEJM 2021."
        ]
        paras, sites, refs = parse_paragraphs_list(lines, citation_format="paren")
        self.assertEqual(len(refs), 1)
        self.assertEqual(len(sites), 1, "Only the authentic citation (1) should be captured")
        self.assertEqual(sites[0].sentence, "Recent genomic guidelines recommend screening (1).")

    def test_40_missing_doi_insertion_in_tracked_docx(self):
        """Verifies that when a reference lacks a DOI, the recovered DOI is inserted into the Word XML as a <w:ins> element."""
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript
        from server.models import ValidationVerdict

        doc = docx.Document()
        doc.add_paragraph("Novel vascular phenotypes are reported (1).")
        doc.add_paragraph("REFERENCES")
        doc.add_paragraph("1. Alpha A, Beta B. Genomic profiling of arteriopathies. Nat Genet. 2020;52(4):300-310.")

        in_buf = BytesIO()
        doc.save(in_buf)
        in_buf.seek(0)

        paras, sites, refs = parse_docx_manuscript(in_buf, citation_format="paren")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].doi, "")

        verdicts = {
            1: ValidationVerdict(
                ref_num=1,
                status="recovered",
                is_reachable=True,
                is_recovered_doi=True,
                recovered_doi="10.1038/s41588-020-0001-x",
                resolved_url="https://doi.org/10.1038/s41588-020-0001-x"
            )
        }

        out_buf = BytesIO()
        link_docx_manuscript(
            BytesIO(in_buf.getvalue()),
            sites, refs,
            verdicts=verdicts,
            output_target=out_buf,
            renumber_ama=True,
            track_changes=True,
            author="Co-Scientist"
        )
        out_buf.seek(0)

        out_doc = docx.Document(out_buf)
        ref_para = [p for p in out_doc.paragraphs if "Alpha A" in p.text][0]
        ins_nodes = ref_para._p.findall(qn('w:ins'))
        self.assertGreaterEqual(len(ins_nodes), 1)
        xml_str = ref_para._p.xml
        self.assertIn("10.1038/s41588-020-0001-x", xml_str)
        self.assertIn("w:ins", xml_str)

    def test_41_in_document_audit_table_generation(self):
        """Verifies that the Co-Scientist Reference Audit & Reachability Ledger table is generated at the end of the manuscript."""
        from server.parser import parse_docx_manuscript
        from server.linker import link_docx_manuscript
        from server.models import ValidationVerdict

        doc = docx.Document()
        doc.add_paragraph("Initial diagnostic cohorts demonstrate high fidelity (1, 2).")
        doc.add_paragraph("REFERENCES")
        doc.add_paragraph("1. Smith J. Diagnostic AI. Radiology 2020. doi: 10.1148/radiol.20200001")
        doc.add_paragraph("2. Jones M. Multi-reader validation. Nature 2021.")

        in_buf = BytesIO()
        doc.save(in_buf)
        in_buf.seek(0)

        paras, sites, refs = parse_docx_manuscript(in_buf, citation_format="paren")
        verdicts = {
            1: ValidationVerdict(ref_num=1, status="verified", is_reachable=True, doi="10.1148/radiol.20200001"),
            2: ValidationVerdict(ref_num=2, status="recovered", is_reachable=True, is_recovered_doi=True, recovered_doi="10.1038/s41586-021-0001-y")
        }

        out_buf = BytesIO()
        link_docx_manuscript(
            BytesIO(in_buf.getvalue()),
            sites, refs,
            verdicts=verdicts,
            output_target=out_buf,
            renumber_ama=True,
            track_changes=False,
            include_audit_ledger=True
        )
        out_buf.seek(0)

        out_doc = docx.Document(out_buf)
        # Verify ledger heading exists
        heading_found = any("Co-Scientist Reference Audit & Reachability Ledger" in p.text for p in out_doc.paragraphs)
        self.assertTrue(heading_found, "Ledger heading must be present in output document")

        # Verify audit table exists and has 5 columns
        self.assertGreaterEqual(len(out_doc.tables), 1, "Must contain at least 1 table (the audit ledger)")
        audit_table = out_doc.tables[-1]
        self.assertEqual(len(audit_table.columns), 5, "Audit table must have 5 columns")
        headers = [c.text.strip() for c in audit_table.rows[0].cells]
        self.assertEqual(headers, ["#", "Bibliographic Record", "DOI Identifier", "Audit Status", "Citations"])

        # Verify data rows
        self.assertEqual(len(audit_table.rows), 3, "Header + 2 reference rows")
        row1_text = " ".join(c.text for c in audit_table.rows[1].cells)
        row2_text = " ".join(c.text for c in audit_table.rows[2].cells)
        self.assertIn("10.1148/radiol.20200001", row1_text)
        self.assertIn("10.1038/s41586-021-0001-y", row2_text)
        self.assertIn("DOI Recovered", row2_text)

    def test_42_zotero_bibliography_field_enclosure(self):
        """
        Verifies authentic multi-paragraph ADDIN ZOTERO_BIBL field enclosure:
        1. REFERENCES header contains begin, CSL_BIBL, and separate, but NOT end.
        2. All bibliography entries are located inside the field between separate and end.
        3. Field properly encloses references in BOTH clean and tracked changes modes.
        4. No duplicate or dangling ZOTERO_BIBL field codes exist.
        """
        from docx.oxml.ns import qn

        # 1. Clean mode on sample radiology manuscript
        doc_path = "sample_radiology_manuscript.docx"
        paras, sites, refs = parse_docx_manuscript(doc_path)
        out_buf = BytesIO()
        link_docx_manuscript(doc_path, sites, refs, output_target=out_buf, track_changes=False)
        out_buf.seek(0)
        doc_clean = docx.Document(out_buf)

        # Locate bibl start paragraph
        bibl_start_idx = None
        for i, p in enumerate(doc_clean.paragraphs):
            instrs = p._p.xpath('.//w:instrText[contains(text(), "ZOTERO_BIBL")]')
            if instrs:
                bibl_start_idx = i
                fc_types = [fc.get(qn('w:fldCharType')) for fc in p._p.xpath('.//w:fldChar')]
                self.assertIn('begin', fc_types, "Header must contain begin")
                self.assertIn('separate', fc_types, "Header must contain separate")
                self.assertNotIn('end', fc_types, "Header must NOT contain end; field must enclose references")
                break
        self.assertIsNotNone(bibl_start_idx, "Must find ADDIN ZOTERO_BIBL header paragraph")

        # Locate bibl end paragraph
        bibl_end_idx = None
        for i in range(bibl_start_idx, len(doc_clean.paragraphs)):
            fc_types = [fc.get(qn('w:fldCharType')) for fc in doc_clean.paragraphs[i]._p.xpath('.//w:fldChar')]
            if 'end' in fc_types:
                bibl_end_idx = i
                break
        self.assertIsNotNone(bibl_end_idx, "Must find bibliography end marker")
        self.assertGreater(bibl_end_idx, bibl_start_idx, "End marker must follow start marker")

        # Verify all references are situated strictly between bibl_start_idx and bibl_end_idx (inclusive)
        ref_count_inside = 0
        for i in range(bibl_start_idx + 1, bibl_end_idx + 1):
            txt = doc_clean.paragraphs[i].text.strip()
            if re.match(r'^\d+\.', txt):
                ref_count_inside += 1
        self.assertEqual(ref_count_inside, len(refs), f"All {len(refs)} references must be inside the field")

        # 2. Tracked Changes mode parity
        out_tracked_buf = BytesIO()
        link_docx_manuscript(doc_path, sites, refs, output_target=out_tracked_buf, track_changes=True)
        out_tracked_buf.seek(0)
        doc_tracked = docx.Document(out_tracked_buf)

        tracked_bibl_start = None
        for i, p in enumerate(doc_tracked.paragraphs):
            instrs = p._p.xpath('.//w:instrText[contains(text(), "ZOTERO_BIBL")]')
            if instrs:
                tracked_bibl_start = i
                fc_types = [fc.get(qn('w:fldCharType')) for fc in p._p.xpath('.//w:fldChar')]
                self.assertIn('begin', fc_types)
                self.assertIn('separate', fc_types)
                self.assertNotIn('end', fc_types)
                break
        self.assertIsNotNone(tracked_bibl_start, "Tracked document must contain ADDIN ZOTERO_BIBL field")

        # 3. Verify real-world ACTA2 manuscript has zero duplicate bibl fields
        acta2_path = "/home/vd00026/Desktop/Zotero_Link/ACTA2_Manuscript_11.14.2026.docx"
        if os.path.exists(acta2_path):
            a_paras, a_sites, a_refs = parse_docx_manuscript(acta2_path)
            a_out = BytesIO()
            link_docx_manuscript(acta2_path, a_sites, a_refs, output_target=a_out, track_changes=False)
            a_out.seek(0)
            a_doc = docx.Document(a_out)
            bibl_instr_count = sum(len(p._p.xpath('.//w:instrText[contains(text(), "ZOTERO_BIBL")]')) for p in a_doc.paragraphs)
            self.assertEqual(bibl_instr_count, 1, "Must contain exactly 1 ADDIN ZOTERO_BIBL field (no duplicates)")

    def test_43_preview_citation_offsets_and_clinical_immunity(self):
        """
        Verifies that citation site matching and preview rendering maintain absolute immunity
        for clinical numbers, patient counts, percentages, and genetic codons:
        1. Exact character offsets (match_start, match_end) are strictly grounded.
        2. Numbers appearing earlier in the sentence ('13 patients', 'p.Arg179', '95.7%')
           are never corrupted or wrapped in citation pills.
        3. Real-world ACTA2 manuscript paragraphs (P52, P68, P80, P83, P84) render with zero
           false-positive pill injections.
        """
        acta2_path = "/home/vd00026/Desktop/Zotero_Link/ACTA2_Manuscript_11.14.2026.docx"
        if not os.path.exists(acta2_path):
            self.skipTest("ACTA2 manuscript file not present")

        paras, sites, refs = parse_docx_manuscript(acta2_path)

        def render_preview_paragraph(text, p_sites):
            # Mirror the exact app.js grounded offset slicing algorithm
            sorted_sites = sorted(p_sites, key=lambda s: s.match_start if hasattr(s, 'match_start') and s.match_start is not None else 0)
            fragments = []
            last_idx = 0
            for s in sorted_sites:
                start = getattr(s, 'match_start', None)
                end = getattr(s, 'match_end', None)
                if start is not None and end is not None and start >= last_idx and end <= len(text) and text[start:end] == s.text:
                    pass
                else:
                    pos = -1
                    if s.context_before:
                        anchor = s.context_before.strip()[-25:]
                        if anchor and anchor in text[last_idx:]:
                            anchor_pos = text.find(anchor, last_idx)
                            candidate = anchor_pos + len(anchor)
                            if text.startswith(s.text, candidate):
                                pos = candidate
                            elif s.text in text[candidate:candidate+6]:
                                pos = candidate + text[candidate:candidate+6].find(s.text)
                    if pos == -1:
                        pos = text.find(s.text, last_idx)
                    if pos != -1 and pos >= last_idx:
                        start = pos
                        end = pos + len(s.text)
                    else:
                        continue
                if start > last_idx:
                    fragments.append(text[last_idx:start])
                fragments.append(f'<span class="cit-pill" data-nums="{",".join(map(str, s.nums))}">{s.text}</span>')
                last_idx = end
            if last_idx < len(text):
                fragments.append(text[last_idx:])
            return "".join(fragments)

        # 1. Inspect P52: must contain "13 patients" as pure text, not "1<span class="cit-pill">3</span> patients"
        p52_text = paras[52]
        p52_sites = [s for s in sites if s.paragraph_idx == 52]
        p52_html = render_preview_paragraph(p52_text, p52_sites)
        self.assertIn("13 patients", p52_html, "P52 must contain '13 patients' as plain text")
        self.assertNotIn('1<span class="cit-pill"', p52_html, "P52 must not turn '13 patients' into a pill")
        self.assertIn("p.Arg179", p52_html, "P52 must contain 'p.Arg179' intact")

        # 2. Inspect P68: must contain "40 females", "15 males", "5 patients", "11 patients", "47 of 60 patients" as pure text
        p68_text = paras[68]
        p68_sites = [s for s in sites if s.paragraph_idx == 68]
        p68_html = render_preview_paragraph(p68_text, p68_sites)
        self.assertIn("11 patients", p68_html, "P68 must contain '11 patients' as plain text")
        self.assertIn("47 of 60 patients", p68_html, "P68 must contain '47 of 60 patients' as plain text")
        self.assertIn('<span class="cit-pill" data-nums="39">39</span>', p68_html, "P68 must correctly wrap citation 39")

        # 3. Inspect P80: must contain "95.7%" and "76.7%" as pure text, not corrupted by citations 5, 6
        p80_text = paras[80]
        p80_sites = [s for s in sites if s.paragraph_idx == 80]
        p80_html = render_preview_paragraph(p80_text, p80_sites)
        self.assertIn("95.7%", p80_html, "P80 must contain '95.7%' as plain text")
        self.assertIn("76.7%", p80_html, "P80 must contain '76.7%' as plain text")

        # 4. Inspect P83: must contain "57.1%" as pure text
        p83_text = paras[83]
        p83_sites = [s for s in sites if s.paragraph_idx == 83]
        p83_html = render_preview_paragraph(p83_text, p83_sites)
        self.assertIn("57.1%", p83_html, "P83 must contain '57.1%' as plain text")

        # 5. Inspect P84: must contain "43.3%" as pure text
        p84_text = paras[84]
        p84_sites = [s for s in sites if s.paragraph_idx == 84]
        p84_html = render_preview_paragraph(p84_text, p84_sites)
        self.assertIn("43.3%", p84_html, "P84 must contain '43.3%' as plain text")

    def test_44_csl_style_switching_ama_vancouver_apa(self):
        """
        Verify multi-style CSL formatting and Word document generation:
        1. Pure CSL formatting parity for AMA, Vancouver, IEEE, Nature, APA 7th, Harvard
        2. Clean and tracked changes Word document linking in Vancouver bracket style [1, 2]
        3. Clean and tracked changes Word document linking in APA 7th author-date style (Smith et al., 2020)
        4. Validation of ADDIN ZOTERO_PREF_1 style IDs and hanging indents for APA.
        """
        from server.csl_formatter import (
            CSL_STYLES,
            format_in_text_for_style,
            format_bibliography_for_style,
            sort_references_for_style
        )

        # 1. Test In-Text Formatters
        ref_mock_1 = ReferenceEntry(
            ref_num=1,
            raw_text="Topol EJ. High-performance medicine: the convergence of human and artificial intelligence. Nat Med. 2019;25(1):44-56.",
            title="High-performance medicine: the convergence of human and artificial intelligence",
            authors=["Topol EJ"],
            journal="Nat Med",
            year="2019",
            doi="10.1038/s41591-018-0300-7"
        )
        ref_mock_2 = ReferenceEntry(
            ref_num=2,
            raw_text="Esteva A, Kuprel B, Novoa RA. Dermatologist-level classification of skin cancer with deep neural networks. Nature. 2017;542(7639):115-118.",
            title="Dermatologist-level classification of skin cancer with deep neural networks",
            authors=["Esteva A", "Kuprel B", "Novoa RA"],
            journal="Nature",
            year="2017",
            doi="10.1038/nature21056"
        )
        ref_mock_3 = ReferenceEntry(
            ref_num=3,
            raw_text="Rajpurkar P, Irvin J. CheXNet: Radiologist-Level Pneumonia Detection on Chest X-Rays with Deep Learning. arXiv. 2017.",
            title="CheXNet: Radiologist-Level Pneumonia Detection on Chest X-Rays with Deep Learning",
            authors=["Rajpurkar P", "Irvin J"],
            journal="arXiv",
            year="2017",
            doi=""
        )

        # AMA
        ama_in = format_in_text_for_style("ama", [1, 2], [ref_mock_1, ref_mock_2])
        self.assertEqual(ama_in["text"], "1,2")
        self.assertTrue(ama_in["is_superscript"])

        # Vancouver Bracket
        vanc_in = format_in_text_for_style("vancouver-bracket", [1, 2], [ref_mock_1, ref_mock_2])
        self.assertEqual(vanc_in["text"], "[1,2]")
        self.assertFalse(vanc_in["is_superscript"])

        # IEEE
        ieee_in = format_in_text_for_style("ieee", [1, 2], [ref_mock_1, ref_mock_2])
        self.assertEqual(ieee_in["text"], "[1], [2]")
        self.assertFalse(ieee_in["is_superscript"])

        # APA 7th (2 authors uses &, 3+ uses et al.)
        apa_single = format_in_text_for_style("apa-7th", [1], [ref_mock_1])
        self.assertEqual(apa_single["text"], "(Topol, 2019)")

        apa_two = format_in_text_for_style("apa-7th", [3], [ref_mock_3])
        self.assertEqual(apa_two["text"], "(Rajpurkar & Irvin, 2017)")

        apa_three = format_in_text_for_style("apa-7th", [2], [ref_mock_2])
        self.assertEqual(apa_three["text"], "(Esteva et al., 2017)")

        apa_multi = format_in_text_for_style("apa-7th", [1, 2], [ref_mock_1, ref_mock_2])
        self.assertEqual(apa_multi["text"], "(Topol, 2019; Esteva et al., 2017)")

        # Harvard (2 authors uses 'and')
        harv_two = format_in_text_for_style("harvard", [3], [ref_mock_3])
        self.assertEqual(harv_two["text"], "(Rajpurkar and Irvin, 2017)")

        # 2. Test Sorting: APA must sort alphabetically
        unsorted = [ref_mock_1, ref_mock_2, ref_mock_3] # Topol (T), Esteva (E), Rajpurkar (R)
        sorted_apa = sort_references_for_style("apa-7th", unsorted, {})
        self.assertEqual([r.authors[0].split()[0] for r in sorted_apa], ["Esteva", "Rajpurkar", "Topol"])

        # 3. Test Word Document Generation with Vancouver Bracket
        paras, sites, references = parse_docx_manuscript(self.docx_file)
        vanc_out = BytesIO()
        link_docx_manuscript(
            self.docx_file,
            sites,
            references,
            output_target=vanc_out,
            renumber_ama=True,
            track_changes=False,
            target_style="vancouver-bracket"
        )
        vanc_docx_bytes = vanc_out.getvalue()
        self.assertGreater(len(vanc_docx_bytes), 1000)
        
        doc_vanc = docx.Document(BytesIO(vanc_docx_bytes))
        doc_vanc_xml = doc_vanc._part._element.xml
        self.assertIn("vancouver", doc_vanc_xml, "Docx must set Zotero pref style to Vancouver")
        self.assertIn("ADDIN ZOTERO_BIBL", doc_vanc_xml, "Docx must contain ZOTERO_BIBL")
        self.assertIn("[1]", doc_vanc_xml, "Docx must contain bracketed in-text citation [1]")

        # 4. Test Word Document Generation with APA 7th
        apa_out = BytesIO()
        link_docx_manuscript(
            self.docx_file,
            sites,
            references,
            output_target=apa_out,
            renumber_ama=False,
            track_changes=False,
            target_style="apa-7th"
        )
        apa_docx_bytes = apa_out.getvalue()
        self.assertGreater(len(apa_docx_bytes), 1000)
        
        doc_apa = docx.Document(BytesIO(apa_docx_bytes))
        doc_apa_xml = doc_apa._part._element.xml
        self.assertIn("apa", doc_apa_xml, "Docx must set Zotero pref style to APA")
        self.assertIn("ADDIN ZOTERO_BIBL", doc_apa_xml, "Docx must contain ZOTERO_BIBL")
        # Check hanging indent w:ind w:left="720" w:hanging="720"
        self.assertIn('w:hanging="720"', doc_apa_xml, "APA bibliography entries must have hanging indents")

        # 5. Test Tracked Changes with Vancouver Bracket
        vanc_tc_out = BytesIO()
        link_docx_manuscript(
            self.docx_file,
            sites,
            references,
            output_target=vanc_tc_out,
            renumber_ama=True,
            track_changes=True,
            target_style="vancouver-bracket"
        )
        vanc_tc_xml = docx.Document(BytesIO(vanc_tc_out.getvalue()))._part._element.xml
        self.assertIn("<w:del", vanc_tc_xml, "Tracked changes mode must emit <w:del>")
        self.assertIn("<w:ins", vanc_tc_xml, "Tracked changes mode must emit <w:ins>")
        self.assertIn("vancouver", vanc_tc_xml, "Must retain Vancouver target style in tracked changes")

        # 6. Test Tracked Changes with APA 7th
        apa_tc_out = BytesIO()
        link_docx_manuscript(
            self.docx_file,
            sites,
            references,
            output_target=apa_tc_out,
            renumber_ama=False,
            track_changes=True,
            target_style="apa-7th"
        )
        apa_tc_xml = docx.Document(BytesIO(apa_tc_out.getvalue()))._part._element.xml
        self.assertIn("<w:del", apa_tc_xml, "APA Tracked changes mode must emit <w:del>")
        self.assertIn("<w:ins", apa_tc_xml, "APA Tracked changes mode must emit <w:ins>")
        self.assertIn("apa", apa_tc_xml, "Must retain APA target style in tracked changes")

    def test_45_radiology_journals_csl_and_extraction(self):
        """
        Verify full support for all major radiology journals (RSNA, ASNR, ARRS, ESR, SIR, ACR):
        1. All 14 radiology styles registered with official Zotero repository IDs
        2. In-text citation formatting: Superscript for RSNA/ASNR/ARRS/SIR, Brackets for ESR/Springer
        3. Word OpenXML linking with target style IDs (radiology, ajnr, ajr, european-radiology)
        4. Journal detection from raw bibliographic citations
        """
        from server.csl_formatter import (
            CSL_STYLES,
            format_in_text_for_style,
            format_bibliography_for_style
        )
        from server.parser import parse_reference_line

        # 1. Verify Registration of all Major Radiology Journals
        rad_styles = [
            ("radiology", "http://www.zotero.org/styles/radiology", "sup"),
            ("ajnr", "http://www.zotero.org/styles/american-journal-of-neuroradiology", "sup"),
            ("ajr", "http://www.zotero.org/styles/american-journal-of-roentgenology", "sup"),
            ("european-radiology", "http://www.zotero.org/styles/european-radiology", "bracket"),
            ("radiographics", "http://www.zotero.org/styles/radiographics", "sup"),
            ("jvir", "http://www.zotero.org/styles/journal-of-vascular-and-interventional-radiology", "sup"),
            ("jacr", "http://www.zotero.org/styles/journal-of-the-american-college-of-radiology", "sup"),
            ("investigative-radiology", "http://www.zotero.org/styles/investigative-radiology", "sup"),
            ("academic-radiology", "http://www.zotero.org/styles/academic-radiology", "sup"),
            ("clinical-radiology", "http://www.zotero.org/styles/clinical-radiology", "sup"),
            ("korean-journal-of-radiology", "http://www.zotero.org/styles/korean-journal-of-radiology", "sup"),
            ("cvir", "http://www.zotero.org/styles/cardiovascular-and-interventional-radiology", "bracket"),
            ("pediatric-radiology", "http://www.zotero.org/styles/pediatric-radiology", "bracket"),
            ("journal-of-nuclear-medicine", "http://www.zotero.org/styles/journal-of-nuclear-medicine", "sup"),
        ]

        ref_mock = ReferenceEntry(
            ref_num=1,
            raw_text="Smith J, Doe A. Deep learning in neuroradiology. AJNR Am J Neuroradiol. 2021;42(3):400-408.",
            title="Deep learning in neuroradiology",
            authors=["Smith J", "Doe A"],
            journal="American Journal of Neuroradiology",
            year="2021",
            doi="10.3174/ajnr.A7000"
        )

        for key, expected_id, expected_kind in rad_styles:
            self.assertIn(key, CSL_STYLES, f"Style '{key}' must be present in CSL_STYLES")
            self.assertEqual(CSL_STYLES[key]["id"], expected_id, f"Style '{key}' ID mismatch")
            
            in_text = format_in_text_for_style(key, [1, 2], [ref_mock])
            if expected_kind == "sup":
                self.assertTrue(in_text["is_superscript"], f"{key} must use superscript in-text citations")
                self.assertEqual(in_text["text"], "1,2")
            else:
                self.assertFalse(in_text["is_superscript"], f"{key} must not use superscript")
                self.assertEqual(in_text["text"], "[1,2]")

        # 2. Test Word Document generation for key radiology journals
        paras, sites, references = parse_docx_manuscript(self.docx_file)

        # Radiology (RSNA)
        out_radiol = BytesIO()
        link_docx_manuscript(self.docx_file, sites, references, output_target=out_radiol, target_style="radiology")
        doc_radiol_xml = docx.Document(BytesIO(out_radiol.getvalue()))._part._element.xml
        self.assertIn("http://www.zotero.org/styles/radiology", doc_radiol_xml)
        self.assertIn("ADDIN ZOTERO_BIBL", doc_radiol_xml)

        # AJNR (American Journal of Neuroradiology)
        out_ajnr = BytesIO()
        link_docx_manuscript(self.docx_file, sites, references, output_target=out_ajnr, target_style="ajnr")
        doc_ajnr_xml = docx.Document(BytesIO(out_ajnr.getvalue()))._part._element.xml
        self.assertIn("american-journal-of-neuroradiology", doc_ajnr_xml)

        # AJR (American Journal of Roentgenology)
        out_ajr = BytesIO()
        link_docx_manuscript(self.docx_file, sites, references, output_target=out_ajr, target_style="ajr")
        doc_ajr_xml = docx.Document(BytesIO(out_ajr.getvalue()))._part._element.xml
        self.assertIn("american-journal-of-roentgenology", doc_ajr_xml)

        # European Radiology (ESR / Springer)
        out_eur = BytesIO()
        link_docx_manuscript(self.docx_file, sites, references, output_target=out_eur, target_style="european-radiology")
        doc_eur_xml = docx.Document(BytesIO(out_eur.getvalue()))._part._element.xml
        self.assertIn("european-radiology", doc_eur_xml)
        self.assertIn("[1]", doc_eur_xml, "European Radiology must format citations with brackets [1]")

        # 3. Test Radiology Journal Extraction
        parsed_ajnr = parse_reference_line(1, "1. Fox C, Stout C. Moyamoya imaging. AJNR Am J Neuroradiol. 2018;39(4):720-726. doi: 10.3174/ajnr.A5500")
        self.assertEqual(parsed_ajnr.journal, "American Journal of Neuroradiology")
        self.assertEqual(parsed_ajnr.journal_abbr, "AJNR Am J Neuroradiol")

        parsed_radiol = parse_reference_line(2, "2. McKinney AM, Palmer CS. Posterior reversible encephalopathy syndrome. Radiology. 2007;244(1):249-257. doi: 10.1148/radiol.2441061099")
        self.assertEqual(parsed_radiol.journal, "Radiology")

        parsed_ajr = parse_reference_line(3, "3. Provenzale JM, Jahan R. Diffusion-weighted imaging in Moyamoya. AJR Am J Roentgenol. 2004;182(2):355-361.")
        self.assertEqual(parsed_ajr.journal, "American Journal of Roentgenology")

        parsed_eur = parse_reference_line(4, "4. Saliou G, Krings T. Pediatric vascular malformations. Eur Radiol. 2014;24(12):3120-3129.")
        self.assertEqual(parsed_eur.journal, "European Radiology")

if __name__ == "__main__":
    unittest.main()

