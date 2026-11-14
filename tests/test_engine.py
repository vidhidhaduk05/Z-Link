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

if __name__ == "__main__":
    unittest.main()
