"""
Word .docx Native Zotero Field Injector & Formatter.
"""
import copy
import json
import random
import re
import string
from io import BytesIO
from typing import List, Dict, Optional, Union
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

def convert_paren_site(p, run_idx: int, match_start: int, match_end: int):
    r = p.runs[run_idx]
    text = r.text
    before, cited, after = text[:match_start], text[match_start:match_end], text[match_end:]
    if before.endswith(' '):
        before = before[:-1]
    sup_text = ','.join(part.replace('–', '-').replace(' ', '')
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
    output_target: Optional[Union[str, BytesIO]] = None
) -> Union[str, BytesIO]:
    """
    Transforms the docx by injecting native Zotero field codes.
    """
    doc = docx.Document(docx_input)
    ref_by_num = {r.ref_num: r for r in references}
    csl_by_num = {r.ref_num: build_csl_record(r, (verdicts or {}).get(r.ref_num)) for r in references}

    # Process citation sites in reverse order so paragraph run indices remain valid
    for s in reversed(sites):
        if s.paragraph_idx >= len(doc.paragraphs):
            continue
        p = doc.paragraphs[s.paragraph_idx]
        if s.kind == 'paren' and s.match_start is not None and s.match_end is not None:
            if s.run_idx < len(p.runs):
                sup_el = convert_paren_site(p, s.run_idx, s.match_start, s.match_end)
            else:
                continue
        elif s.run_idx < len(p.runs):
            sup_el = p.runs[s.run_idx]._r
        else:
            continue

        citation_items = []
        for n in s.nums:
            csl_data = csl_by_num.get(n, {})
            key = f"zotero_key_{n}"
            citation_items.append({
                "id": key,
                "uris": [f"http://zotero.org/users/0/items/{key}"],
                "itemData": csl_data
            })

        citation_json = {
            "citationID": ''.join(random.choices(string.ascii_letters + string.digits, k=8)),
            "properties": {
                "formattedCitation": sup_el.xpath('string(.)'),
                "plainCitation": sup_el.xpath('string(.)'),
                "noteIndex": 0
            },
            "citationItems": citation_items,
            "schema": CSL_CITATION_SCHEMA
        }
        inject_citation_field(sup_el, citation_json)

    # Locate reference list paragraphs
    ref_start_re = re.compile(r'^\d{1,3}\.\s')
    ref_paras = [p for p in doc.paragraphs if ref_start_re.match(p.text.strip())]
    if ref_paras:
        inject_bibliography_field(doc, ref_paras[0], ref_paras[-1])

    # Inject AMA doc prefs
    inject_doc_prefs(doc, DEFAULT_STYLE, DEFAULT_STYLE_NAME, library_id=1)

    target = output_target or BytesIO()
    doc.save(target)
    return target
