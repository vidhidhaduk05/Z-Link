"""
Word .docx Native Zotero Field Injector & Formatter.
"""
import copy
import json
import random
import re
import string
from io import BytesIO
from typing import List, Dict, Optional, Union, Tuple
import docx
from docx.oxml.ns import qn
from lxml import etree
from server.models import CitationSite, ReferenceEntry, ValidationVerdict

DEFAULT_STYLE = "http://www.zotero.org/styles/american-medical-association"
DEFAULT_STYLE_NAME = "American Medical Association 11th edition"
CSL_CITATION_SCHEMA = "https://github.com/citation-style-language/schema/raw/master/csl-citation.json"

def fld_run(kind: str, instr: Optional[str] = None):
    r = etree.Element(qn('w:r'))
    rPr = etree.SubElement(r, qn('w:rPr'))
    etree.SubElement(rPr, qn('w:vanish'))
    if kind in ('begin', 'separate', 'end'):
        fc = etree.SubElement(r, qn('w:fldChar'))
        fc.set(qn('w:fldCharType'), kind)
    else:
        it = etree.SubElement(r, qn('w:instrText'))
        it.set(qn('xml:space'), 'preserve')
        it.text = f" {instr} "
    return r

def make_sup_run(model_run, text: str):
    new_r = copy.deepcopy(model_run._r)
    for t in new_r.findall(qn('w:t')):
        new_r.remove(t)
    rPr = new_r.find(qn('w:rPr'))
    if rPr is None:
        rPr = new_r.makeelement(qn('w:rPr'), {})
        new_r.insert(0, rPr)
    for va in rPr.findall(qn('w:vertAlign')):
        rPr.remove(va)
    va = rPr.makeelement(qn('w:vertAlign'), {})
    va.set(qn('w:val'), 'superscript')
    rPr.append(va)
    t = new_r.makeelement(qn('w:t'), {})
    t.text = text
    t.set(qn('xml:space'), 'preserve')
    new_r.append(t)
    return new_r

def make_text_run(model_run, text: str):
    new_r = copy.deepcopy(model_run._r)
    for t in new_r.findall(qn('w:t')):
        new_r.remove(t)
    rPr = new_r.find(qn('w:rPr'))
    if rPr is not None:
        for va in rPr.findall(qn('w:vertAlign')):
            rPr.remove(va)
    t = new_r.makeelement(qn('w:t'), {})
    t.text = text
    t.set(qn('xml:space'), 'preserve')
    new_r.append(t)
    return new_r

def convert_paren_site(p, run_idx: int, match_start: int, match_end: int, formatted_text: Optional[str] = None):
    r = p.runs[run_idx]
    text = r.text
    before, cited, after = text[:match_start], text[match_start:match_end], text[match_end:]
    if before.endswith(' '):
        before = before[:-1]
    sup_text = formatted_text if formatted_text is not None else ','.join(part.replace('–', '-').replace(' ', '')
                        for part in cited[1:-1].split(','))
    lead_punct = ''
    if after and after[0] in '.,;:':
        lead_punct, after = after[0], after[1:]
    r.text = before + lead_punct
    sup_r = make_sup_run(r, sup_text)
    r._r.addnext(sup_r)
    if after:
        sup_r.addnext(make_text_run(r, after))
    return sup_r

def format_condensed_citation(nums: List[int]) -> str:
    """
    Format a list of reference numbers into standard AMA notation.
    Contiguous runs of 3+ use hyphens (e.g. 1-3), pairs use commas (1,2).
    """
    if not nums:
        return ""
    sorted_unique = sorted(set(nums))
    ranges = []
    start = sorted_unique[0]
    end = start

    for n in sorted_unique[1:]:
        if n == end + 1:
            end = n
        else:
            if end - start >= 2:
                ranges.append(f"{start}-{end}")
            elif end - start == 1:
                ranges.append(f"{start},{end}")
            else:
                ranges.append(f"{start}")
            start = n
            end = n

    if end - start >= 2:
        ranges.append(f"{start}-{end}")
    elif end - start == 1:
        ranges.append(f"{start},{end}")
    else:
        ranges.append(f"{start}")

    return ",".join(ranges)

def build_ama_renumbering_map(
    references: List[ReferenceEntry],
    sites: List[CitationSite]
) -> Tuple[Dict[int, int], List[int], List[int]]:
    """
    Construct the bijective permutation map pi: OldRefNum -> NewRefNum.
    References are numbered 1, 2, 3... in the exact order of their first mention in the text.
    Any uncited references in the bibliography are assigned consecutive numbers at the end.
    """
    ref_nums = [r.ref_num for r in references]
    first_seen_order: List[int] = []
    seen_set = set()

    for site in sites:
        for num in site.nums:
            if num not in seen_set and num in ref_nums:
                seen_set.add(num)
                first_seen_order.append(num)

    for site in sites:
        for num in site.nums:
            if num not in seen_set:
                seen_set.add(num)
                first_seen_order.append(num)

    uncited = [n for n in ref_nums if n not in seen_set]

    mapping: Dict[int, int] = {}
    for idx, old_num in enumerate(first_seen_order):
        mapping[old_num] = idx + 1

    start_uncited = len(first_seen_order) + 1
    for idx, old_num in enumerate(uncited):
        mapping[old_num] = start_uncited + idx

    return mapping, first_seen_order, uncited

def inject_citation_field(sup_run_element, citation_json: Dict):
    instr = "ADDIN ZOTERO_ITEM CSL_CITATION " + json.dumps(citation_json, ensure_ascii=False)
    sup_run_element.addprevious(fld_run('begin'))
    sup_run_element.addprevious(fld_run('instr', instr))
    sup_run_element.addprevious(fld_run('separate'))
    sup_run_element.addnext(fld_run('end'))

def inject_bibliography_field(doc, first_para, last_para):
    instr = 'ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} CSL_BIBLIOGRAPHY'
    p_first, p_last = first_para._p, last_para._p
    pPr = p_first.find(qn('w:pPr'))
    prev = pPr
    for e in (fld_run('begin'), fld_run('instr', instr), fld_run('separate')):
        if prev is None:
            p_first.insert(0, e)
        else:
            prev.addnext(e)
        prev = e
    p_last.append(fld_run('end'))

def inject_doc_prefs(doc, style_id=DEFAULT_STYLE, style_name=DEFAULT_STYLE_NAME, library_id=1):
    prefs = {
        "styleName": style_name,
        "styleId": style_id,
        "locale": "en-US",
        "libraryID": library_id,
        "templateVersion": 1,
        "purge": False,
        "noteStyle": 0,
        "bibliographyStyle": 0
    }
    instr = "ADDIN ZOTERO_PREF_1 " + json.dumps(prefs, ensure_ascii=False)
    first_p = doc.paragraphs[0]._p
    pPr = first_p.find(qn('w:pPr'))
    prev = pPr
    for e in (fld_run('begin'), fld_run('instr', instr), fld_run('separate'), fld_run('end')):
        if prev is None:
            first_p.insert(0, e)
        else:
            prev.addnext(e)
        prev = e

def build_csl_record(ref: ReferenceEntry, verdict: Optional[ValidationVerdict] = None) -> Dict:
    title = (verdict.crossref_title if verdict and verdict.crossref_title else ref.title) or "Article"
    journal = (verdict.crossref_journal if verdict and verdict.crossref_journal else ref.journal) or ""
    year = (verdict.crossref_year if verdict and verdict.crossref_year else ref.year) or "2020"
    vol = (verdict.crossref_volume if verdict and verdict.crossref_volume else ref.volume) or ""
    issue = (verdict.crossref_issue if verdict and verdict.crossref_issue else ref.issue) or ""
    pages = (verdict.crossref_pages if verdict and verdict.crossref_pages else ref.pages) or ""
    doi = ref.doi or ""

    authors = (verdict.crossref_authors if verdict and verdict.crossref_authors else ref.authors) or ["Author"]
    author_list = []
    for a in authors:
        parts = a.split(" ", 1)
        if len(parts) == 2:
            author_list.append({"family": parts[0], "given": parts[1]})
        else:
            author_list.append({"family": a, "given": ""})

    return {
        "id": f"ITEM-{ref.ref_num}",
        "type": "article-journal",
        "title": title,
        "container-title": journal,
        "volume": vol,
        "issue": issue,
        "page": pages,
        "DOI": doi,
        "issued": {"date-parts": [[int(year)] if year.isdigit() else [2020]]},
        "author": author_list
    }

def link_docx_manuscript(
    docx_input: Union[str, BytesIO],
    sites: List[CitationSite],
    references: List[ReferenceEntry],
    verdicts: Optional[Dict[int, ValidationVerdict]] = None,
    output_target: Optional[Union[str, BytesIO]] = None,
    renumber_ama: bool = True
) -> Union[str, BytesIO]:
    """
    Transforms the docx by injecting native Zotero field codes.
    When renumber_ama is True, re-numbers in-text citations consecutively (first cited = #1)
    and re-orders the bibliography paragraphs accordingly.
    """
    doc = docx.Document(docx_input)
    ref_by_num = {r.ref_num: r for r in references}

    # Compute AMA sequential re-numbering permutation map
    if renumber_ama:
        mapping, first_seen_order, uncited = build_ama_renumbering_map(references, sites)
    else:
        mapping = {r.ref_num: r.ref_num for r in references}

    # Build CSL records indexed by new reference number
    csl_by_new_num = {}
    for old_n, new_n in mapping.items():
        if old_n in ref_by_num:
            ref_entry = ref_by_num[old_n]
            v = (verdicts or {}).get(old_n)
            rec = build_csl_record(ref_entry, v)
            rec["id"] = f"ITEM-{new_n}"
            csl_by_new_num[new_n] = rec

    # Process citation sites in reverse order so paragraph run indices remain valid
    for s in reversed(sites):
        if s.paragraph_idx >= len(doc.paragraphs):
            continue
        p = doc.paragraphs[s.paragraph_idx]

        # Calculate new numbers and AMA condensed representation
        new_site_nums = sorted(list(set(mapping.get(n, n) for n in s.nums)))
        condensed_str = format_condensed_citation(new_site_nums)

        if s.kind in ('paren', 'bracket') and s.match_start is not None and s.match_end is not None:
            if s.run_idx < len(p.runs):
                sup_el = convert_paren_site(p, s.run_idx, s.match_start, s.match_end, formatted_text=condensed_str)
            else:
                continue
        elif s.run_idx < len(p.runs):
            sup_run = p.runs[s.run_idx]
            sup_el = sup_run._r
            sup_run.text = condensed_str
        else:
            continue

        citation_items = []
        for new_n in new_site_nums:
            csl_data = csl_by_new_num.get(new_n, {})
            key = f"zotero_key_{new_n}"
            citation_items.append({
                "id": key,
                "uris": [f"http://zotero.org/users/0/items/{key}"],
                "itemData": csl_data
            })

        citation_json = {
            "citationID": ''.join(random.choices(string.ascii_letters + string.digits, k=8)),
            "properties": {
                "formattedCitation": condensed_str,
                "plainCitation": condensed_str,
                "noteIndex": 0
            },
            "citationItems": citation_items,
            "schema": CSL_CITATION_SCHEMA
        }
        inject_citation_field(sup_el, citation_json)

    # Reorder and renumber bibliography paragraphs in the Word XML
    ref_start_re = re.compile(r'^(\d{1,3})\.\s*(.*)$')
    ref_paras_info = []
    for p in doc.paragraphs:
        m = ref_start_re.match(p.text.strip())
        if m:
            old_n = int(m.group(1))
            new_n = mapping.get(old_n, old_n)
            ref_paras_info.append((old_n, new_n, p, m))

    if ref_paras_info:
        # Re-number the prefix of each paragraph: replace "old_n. " with "new_n. "
        for old_n, new_n, p, m in ref_paras_info:
            old_prefix = m.group(1) + "."
            new_prefix = f"{new_n}."
            rest_content = m.group(2)
            replaced = False
            for r in p.runs:
                if old_prefix in r.text:
                    r.text = r.text.replace(old_prefix, new_prefix, 1)
                    replaced = True
                    break
            if not replaced and p.runs:
                p.runs[0].text = f"{new_n}. " + rest_content
                for r in p.runs[1:]:
                    r.text = ""

        # Re-order the paragraphs in the document XML according to new_n
        if renumber_ama and len(ref_paras_info) > 1:
            first_p_elem = ref_paras_info[0][2]._p
            parent = first_p_elem.getparent()
            if parent is not None:
                insert_idx = parent.index(first_p_elem)
                sorted_by_new = sorted(ref_paras_info, key=lambda item: item[1])
                for idx, (old_n, new_n, p, m) in enumerate(sorted_by_new):
                    parent.insert(insert_idx + idx, p._p)
                inject_bibliography_field(doc, sorted_by_new[0][2], sorted_by_new[-1][2])
            else:
                inject_bibliography_field(doc, ref_paras_info[0][2], ref_paras_info[-1][2])
        else:
            inject_bibliography_field(doc, ref_paras_info[0][2], ref_paras_info[-1][2])

    # Inject AMA doc prefs
    inject_doc_prefs(doc, DEFAULT_STYLE, DEFAULT_STYLE_NAME, library_id=1)

    target = output_target or BytesIO()
    doc.save(target)
    return target

