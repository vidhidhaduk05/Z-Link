"""
Integration and Unit Tests for Reference Parsing, Reachability Validation, and Field Injection.
"""
import os
import sys
import unittest
import docx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server.parser import parse_docx_manuscript
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

if __name__ == "__main__":
    unittest.main()

