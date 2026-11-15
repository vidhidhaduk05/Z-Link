"""
Word .docx Native Zotero Field Injector & Formatter.
"""
import copy
import json
import random
import re
import string
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Dict, Optional, Union, Tuple, Any
import docx
from docx.shared import Pt, Inches, RGBColor
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn
from lxml import etree
from server.models import CitationSite, ReferenceEntry, ValidationVerdict

DEFAULT_STYLE = "http://www.zotero.org/styles/american-medical-association"
DEFAULT_STYLE_NAME = "American Medical Association 11th edition"
CSL_CITATION_SCHEMA = "https://github.com/citation-style-language/schema/raw/master/csl-citation.json"

class RevisionTracker:
    """Manages unique revision IDs and author attribution for Word OpenXML Track Changes."""
    def __init__(self, author: str = "Co-Scientist", date_str: Optional[str] = None):
        self.author = author
        self.date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._current_id = 1

    def next_id(self) -> str:
        res = str(self._current_id)
        self._current_id += 1
        return res

def make_del_element(text: str, rev_id: str, author: str = "Co-Scientist", date_str: Optional[str] = None, is_superscript: bool = False, model_run=None):
    """Creates a native OpenXML <w:del> element with <w:delText>."""
    del_el = etree.Element(qn('w:del'))
    del_el.set(qn('w:id'), rev_id)
    del_el.set(qn('w:author'), author)
    del_el.set(qn('w:date'), date_str or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    r = copy.deepcopy(model_run._r) if model_run is not None else etree.Element(qn('w:r'))
    for t in r.findall(qn('w:t')):
        r.remove(t)
    for dt in r.findall(qn('w:delText')):
        r.remove(dt)

    rPr = r.find(qn('w:rPr'))
    if is_superscript:
        if rPr is None:
            rPr = etree.SubElement(r, qn('w:rPr'))
        for va in rPr.findall(qn('w:vertAlign')):
            rPr.remove(va)
        va = etree.SubElement(rPr, qn('w:vertAlign'))
        va.set(qn('w:val'), 'superscript')

    dt = etree.SubElement(r, qn('w:delText'))
    dt.set(qn('xml:space'), 'preserve')
    dt.text = text
    del_el.append(r)
    return del_el

def make_ins_element(text: str, rev_id: str, author: str = "Co-Scientist", date_str: Optional[str] = None, is_superscript: bool = False, model_run=None):
    """Creates a native OpenXML <w:ins> element with <w:t>."""
    ins_el = etree.Element(qn('w:ins'))
    ins_el.set(qn('w:id'), rev_id)
    ins_el.set(qn('w:author'), author)
    ins_el.set(qn('w:date'), date_str or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    r = copy.deepcopy(model_run._r) if model_run is not None else etree.Element(qn('w:r'))
    for t in r.findall(qn('w:t')):
        r.remove(t)

    rPr = r.find(qn('w:rPr'))
    if is_superscript:
        if rPr is None:
            rPr = etree.SubElement(r, qn('w:rPr'))
        for va in rPr.findall(qn('w:vertAlign')):
            rPr.remove(va)
        va = etree.SubElement(rPr, qn('w:vertAlign'))
        va.set(qn('w:val'), 'superscript')

    t = etree.SubElement(r, qn('w:t'))
    t.set(qn('xml:space'), 'preserve')
    t.text = text
    ins_el.append(r)
    return ins_el

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

def convert_paren_site(
    p, run_idx: int, match_start: int, match_end: int,
    formatted_text: Optional[str] = None,
    track_changes: bool = False,
    tracker: Optional[RevisionTracker] = None,
    model_run=None
):
    if model_run is not None:
        r = model_run
    else:
        active_runs = [docx.text.run.Run(r_el, p) for r_el in p._p.xpath('.//w:r[not(ancestor::w:del)]')]
        if run_idx < len(active_runs):
            r = active_runs[run_idx]
        elif run_idx < len(p.runs):
            r = p.runs[run_idx]
        else:
            return None

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

    if track_changes and tracker:
        del_el = make_del_element(cited, tracker.next_id(), tracker.author, tracker.date_str, model_run=r)
        ins_el = make_ins_element(sup_text, tracker.next_id(), tracker.author, tracker.date_str, is_superscript=True, model_run=r)
        
        parent = r._r.getparent()
        if parent is not None and parent.tag == qn('w:ins'):
            p_el = parent.getparent()
            ins_idx = p_el.index(parent)
            after_runs = list(parent)[parent.index(r._r)+1:]
            if after_runs:
                ins_after = copy.deepcopy(parent)
                for c in list(ins_after):
                    ins_after.remove(c)
                for ar in after_runs:
                    parent.remove(ar)
                    ins_after.append(ar)
                p_el.insert(ins_idx + 1, ins_after)
            p_el.insert(ins_idx + 1, ins_el)
            p_el.insert(ins_idx + 1, del_el)
            if after:
                ins_el.addnext(make_text_run(r, after))
            return ins_el
        else:
            r._r.addnext(del_el)
            del_el.addnext(ins_el)
            if after:
                ins_el.addnext(make_text_run(r, after))
            return ins_el
    else:
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

REF_HEADER_RE = re.compile(r'^\s*(?:REFERENCES|Reference List|Bibliography|Works Cited)\s*$', re.I)
POST_REF_HEADER_RE = re.compile(
    r'^\s*(?:Supplementary\s+|Supplemental\s+|Appendix\b|Appendices\b|Tables?\b|Figure\s+Legends?|Figures?\b|Author\s+Contributions|Funding\b|Conflict(?:s)?\s+of\s+Interest|IRB\s+Statement|Informed\s+Consent)',
    re.I
)
REF_START_RE = re.compile(r'^(\d{1,3})\.\s*(.*)$')

class AtomicReferenceBlock:
    def __init__(self, old_n: int, new_n: int, primary_para, match_obj):
        self.old_n = old_n
        self.new_n = new_n
        self.primary_para = primary_para
        self.match_obj = match_obj
        self.paragraphs = [primary_para]

def find_reference_section_bounds(doc) -> Tuple[Optional[int], int, int]:
    """
    Locates the reference section in doc.paragraphs.
    Returns (header_idx, start_idx, end_idx) where:
    - header_idx: index of the 'REFERENCES' paragraph (or None if not found)
    - start_idx: index of the first reference paragraph
    - end_idx: index after the last reference paragraph (exclusive boundary)
    """
    header_idx = None
    start_idx = None
    end_idx = None

    for i, p in enumerate(doc.paragraphs):
        txt = p.text.strip()
        if REF_HEADER_RE.match(txt):
            header_idx = i
            start_idx = i + 1
            break

    if start_idx is None:
        for i, p in enumerate(doc.paragraphs):
            txt = p.text.strip()
            m = REF_START_RE.match(txt)
            if m and int(m.group(1)) == 1:
                from server.parser import is_authentic_bibliographic_reference
                if is_authentic_bibliographic_reference(m.group(2)):
                    start_idx = i
                    break

    if start_idx is None:
        return None, 0, len(doc.paragraphs)

    for i in range(start_idx, len(doc.paragraphs)):
        txt = doc.paragraphs[i].text.strip()
        if POST_REF_HEADER_RE.match(txt):
            end_idx = i
            break

    if end_idx is None:
        end_idx = len(doc.paragraphs)

    return header_idx, start_idx, end_idx

def extract_atomic_reference_blocks(
    paragraphs: List,
    mapping: Dict[int, int]
) -> List[AtomicReferenceBlock]:
    """
    Extracts atomic reference blocks from candidate reference paragraphs.
    Continuation paragraphs (e.g. wrapped DOIs, URLs, multi-line entries)
    are bound to their parent reference entry so they reorder together.
    """
    blocks: List[AtomicReferenceBlock] = []
    current_block: Optional[AtomicReferenceBlock] = None

    for p in paragraphs:
        txt = p.text.strip()
        if not txt:
            continue
        m = REF_START_RE.match(txt)
        if m:
            old_n = int(m.group(1))
            new_n = mapping.get(old_n, old_n)
            current_block = AtomicReferenceBlock(old_n, new_n, p, m)
            blocks.append(current_block)
        elif current_block is not None:
            current_block.paragraphs.append(p)

    return blocks

def strip_existing_bibliography_fields(doc):
    """
    Safely strips pre-existing ADDIN ZOTERO_BIBL field codes (begin, instr, separate, and associated end)
    so re-injecting does not create nested, duplicated, or corrupted field markers.
    """
    bibl_found = False
    for p in doc.paragraphs:
        p_el = p._p
        instrs = p_el.xpath('.//w:instrText[contains(text(), "ZOTERO_BIBL")]')
        if instrs:
            bibl_found = True
            runs_to_remove = set()
            for it in instrs:
                r = it.getparent()
                if r is not None and r.tag == qn('w:r'):
                    runs_to_remove.add(r)
                    prev = r.getprevious()
                    while prev is not None:
                        if prev.tag == qn('w:r') and prev.xpath('.//w:fldChar[@w:fldCharType="begin"]'):
                            runs_to_remove.add(prev)
                            break
                        prev = prev.getprevious()
                    nxt = r.getnext()
                    while nxt is not None:
                        if nxt.tag == qn('w:r') and nxt.xpath('.//w:fldChar[@w:fldCharType="separate"]'):
                            runs_to_remove.add(nxt)
                            sub_nxt = nxt.getnext()
                            while sub_nxt is not None:
                                if sub_nxt.tag == qn('w:r') and sub_nxt.xpath('.//w:fldChar[@w:fldCharType="end"]'):
                                    runs_to_remove.add(sub_nxt)
                                    break
                                sub_nxt = sub_nxt.getnext()
                            break
                        elif nxt.tag == qn('w:r') and nxt.xpath('.//w:fldChar[@w:fldCharType="end"]'):
                            runs_to_remove.add(nxt)
                            break
                        nxt = nxt.getnext()

            for r in runs_to_remove:
                parent = r.getparent()
                if parent is not None:
                    parent.remove(r)

    if bibl_found:
        for p in doc.paragraphs:
            p_el = p._p
            if not p.text.strip():
                end_chars = p_el.xpath('.//w:fldChar[@w:fldCharType="end"]')
                if end_chars:
                    for ec in end_chars:
                        r = ec.getparent()
                        if r is not None and r.getparent() is not None:
                            r.getparent().remove(r)

def inject_bibliography_field(doc, target_para=None, last_para=None, *args, **kwargs):
    """
    Authentically injects multi-paragraph ADDIN ZOTERO_BIBL field codes enclosing the reference list.
    1. Header paragraph receives: begin, instrText, separate
    2. Reference entries reside inside the field
    3. Trailing paragraph receives: end
    """
    if target_para is None and len(doc.paragraphs) > 0:
        target_para = doc.paragraphs[-1]
    if target_para is None:
        return

    strip_existing_bibliography_fields(doc)

    instr = ' ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} CSL_BIBL {"schema":"https://github.com/citation-style-language/schema/raw/master/csl-bibliography.json","bibliography":{"formattedCitation":"","uncited":[],"omitted":[],"custom":[]}} '
    p = target_para._p
    p.append(fld_run('begin'))
    p.append(fld_run('instr', instr))
    p.append(fld_run('separate'))

    if last_para is not None:
        next_p = last_para._p.getnext()
        if next_p is not None and next_p.tag == qn('w:p') and not ''.join(next_p.itertext()).strip():
            next_p.append(fld_run('end'))
        else:
            # Place end at the end of last_para (before sectPr if present)
            last_p_el = last_para._p
            sect_pr = last_p_el.find(qn('w:sectPr'))
            end_r = fld_run('end')
            if sect_pr is not None:
                sect_pr.addprevious(end_r)
            else:
                last_p_el.append(end_r)
    else:
        p.append(fld_run('end'))

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

def append_audit_ledger_to_docx(
    doc: docx.Document,
    references: List[ReferenceEntry],
    verdicts: Optional[Dict[int, Any]] = None,
    mappings: Optional[Dict[int, Any]] = None,
    mapping: Optional[Dict[int, int]] = None
):
    """
    Appends a formal 'Co-Scientist Reference Audit & Reachability Ledger'
    at the end of the manuscript document.
    """
    if not references:
        return

    # Add spacing and heading
    p_head = doc.add_paragraph()
    p_head.paragraph_format.space_before = Pt(24)
    p_head.paragraph_format.space_after = Pt(4)
    r_head = p_head.add_run("Co-Scientist Reference Audit & Reachability Ledger")
    r_head.bold = True
    r_head.font.size = Pt(13)
    r_head.font.color.rgb = RGBColor(0x3A, 0x0F, 0x34)  # Primary Wine

    # Subtitle / Metadata
    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_after = Pt(12)
    r_sub = p_sub.add_run(
        f"Independent scholarly verification across Crossref, DOI Foundation Handle Registry, Europe PMC, and OpenAlex. "
        f"Audited {len(references)} bibliography references. Formatted for peer review verification."
    )
    r_sub.font.size = Pt(9.5)
    r_sub.font.italic = True
    r_sub.font.color.rgb = RGBColor(0x62, 0x53, 0x5D)

    # 5-column table
    table = doc.add_table(rows=1, cols=5)
    table.style = 'Table Grid'
    table.autofit = False

    hdr_cells = table.rows[0].cells
    hdr_titles = ["#", "Bibliographic Record", "DOI Identifier", "Audit Status", "Citations"]
    col_widths = [Inches(0.9), Inches(3.2), Inches(1.8), Inches(1.4), Inches(0.8)]

    for idx, (title, width) in enumerate(zip(hdr_titles, col_widths)):
        hdr_cells[idx].text = title
        hdr_cells[idx].width = width
        shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="3A0F34"/>')
        hdr_cells[idx]._tc.get_or_add_tcPr().append(shd)
        for p in hdr_cells[idx].paragraphs:
            for r in p.runs:
                r.font.bold = True
                r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                r.font.size = Pt(9)

    sorted_refs = list(references)
    if mapping:
        sorted_refs.sort(key=lambda r: mapping.get(r.ref_num, r.ref_num))

    for r_item in sorted_refs:
        old_n = r_item.ref_num
        new_n = (mapping or {}).get(old_n, old_n)
        v = (verdicts or {}).get(old_n)
        m = (mappings or {}).get(old_n)

        v_status = getattr(v, 'status', '') if v else ''
        is_rec = getattr(v, 'is_recovered_doi', False) or getattr(v, 'is_recovered', False) if v else False
        is_bot = getattr(v, 'is_bot_gated', False) if v else False
        is_reach = getattr(v, 'is_reachable', False) if v else False
        doi_val = (getattr(v, 'recovered_doi', '') or getattr(v, 'doi', '') or getattr(r_item, 'doi', '') or '').strip()

        if is_rec or v_status == 'recovered':
            status_text = "DOI Recovered"
        elif is_bot or v_status == 'bot_protected':
            status_text = "Bot Gated / Paywall"
        elif is_reach or v_status == 'verified':
            status_text = "Verified Live (200 OK)"
        elif v_status == 'unreachable':
            status_text = "Unreachable (404)"
        elif not doi_val:
            status_text = "Missing DOI"
        else:
            status_text = "Verified"

        cit_count = 0
        if m:
            cit_count = len(getattr(m, 'occurrences', []) if hasattr(m, 'occurrences') else m.get('occurrences', []))

        row_cells = table.add_row().cells
        for idx, width in enumerate(col_widths):
            row_cells[idx].width = width

        num_str = f"[{new_n}]" if new_n == old_n else f"[{new_n}] (Orig {old_n})"
        row_cells[0].text = num_str

        rec_title = getattr(v, 'crossref_title', '') or getattr(r_item, 'title', '') or r_item.raw_text[:80]
        row_cells[1].text = rec_title

        row_cells[2].text = doi_val if doi_val else "None"
        row_cells[3].text = status_text
        row_cells[4].text = f"{cit_count}x"

        for c in row_cells:
            for p in c.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(8.5)
                    r.font.color.rgb = RGBColor(0x4F, 0x44, 0x4B)

def link_docx_manuscript(
    docx_input: Union[str, BytesIO],
    sites: List[CitationSite],
    references: List[ReferenceEntry],
    verdicts: Optional[Dict[int, ValidationVerdict]] = None,
    output_target: Optional[Union[str, BytesIO]] = None,
    renumber_ama: bool = True,
    track_changes: bool = False,
    author: str = "Co-Scientist",
    mappings: Optional[Dict[int, Any]] = None,
    include_audit_ledger: bool = False
) -> Union[str, BytesIO]:
    """
    Transforms the docx by injecting native Zotero field codes.
    When renumber_ama is True, re-numbers in-text citations consecutively (first cited = #1)
    and re-orders the bibliography paragraphs accordingly.
    When track_changes is True, records all modifications using native OpenXML <w:del> and <w:ins>
    tags attributed to author, enabling Word's revision tracking mode.
    """
    doc = docx.Document(docx_input)
    ref_by_num = {r.ref_num: r for r in references}
    tracker = RevisionTracker(author=author) if track_changes else None

    if track_changes:
        settings_el = doc.settings._element
        if settings_el.find(qn('w:trackRevisions')) is None:
            settings_el.append(etree.Element(qn('w:trackRevisions')))

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

        active_runs = [docx.text.run.Run(r_el, p) for r_el in p._p.xpath('.//w:r[not(ancestor::w:del)]')]
        if s.kind in ('paren', 'bracket') and s.match_start is not None and s.match_end is not None:
            if s.run_idx < len(active_runs):
                sup_el = convert_paren_site(
                    p, s.run_idx, s.match_start, s.match_end,
                    formatted_text=condensed_str,
                    track_changes=track_changes,
                    tracker=tracker,
                    model_run=active_runs[s.run_idx]
                )
            else:
                continue
        elif s.run_idx < len(active_runs):
            sup_run = active_runs[s.run_idx]
            if track_changes and tracker:
                old_text = sup_run.text
                if old_text != condensed_str:
                    del_el = make_del_element(old_text, tracker.next_id(), tracker.author, tracker.date_str, is_superscript=True, model_run=sup_run)
                    ins_el = make_ins_element(condensed_str, tracker.next_id(), tracker.author, tracker.date_str, is_superscript=True, model_run=sup_run)
                    
                    parent = sup_run._r.getparent()
                    if parent is not None and parent.tag == qn('w:ins'):
                        p_el = parent.getparent()
                        ins_idx = p_el.index(parent)
                        after_runs = list(parent)[parent.index(sup_run._r)+1:]
                        if after_runs:
                            ins_after = copy.deepcopy(parent)
                            for c in list(ins_after):
                                ins_after.remove(c)
                            for ar in after_runs:
                                parent.remove(ar)
                                ins_after.append(ar)
                            p_el.insert(ins_idx + 1, ins_after)
                        parent.remove(sup_run._r)
                        p_el.insert(ins_idx + 1, ins_el)
                        p_el.insert(ins_idx + 1, del_el)
                        sup_el = ins_el
                    else:
                        sup_run._r.addnext(del_el)
                        del_el.addnext(ins_el)
                        sup_run.text = ""
                        sup_el = ins_el
                else:
                    sup_el = sup_run._r
            else:
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
    header_idx, start_idx, end_idx = find_reference_section_bounds(doc)
    candidate_paras = doc.paragraphs[start_idx:end_idx]
    blocks = extract_atomic_reference_blocks(candidate_paras, mapping)

    if blocks:
        # Re-number the prefix of each reference block: replace "old_n." with "new_n."
        for b in blocks:
            old_n = b.old_n
            new_n = b.new_n
            p = b.primary_para
            m = b.match_obj

            old_prefix = f"{old_n}."
            new_prefix = f"{new_n}."
            rest_content = m.group(2)

            # Check if reference has a recovered DOI that should be added
            v = (verdicts or {}).get(old_n)
            recovered_doi = None
            candidate_doi = ""
            if v:
                if hasattr(v, 'recovered_doi') and v.recovered_doi:
                    candidate_doi = v.recovered_doi.strip()
                elif hasattr(v, 'doi') and v.doi:
                    candidate_doi = v.doi.strip()
                elif isinstance(v, dict):
                    candidate_doi = (v.get('recovered_doi') or v.get('doi') or '').strip()

            if not candidate_doi:
                ref_obj = next((r for r in (references or []) if r.ref_num == old_n), None)
                if ref_obj and getattr(ref_obj, 'doi', None):
                    candidate_doi = ref_obj.doi.strip()

            if candidate_doi:
                clean_doi_key = re.sub(r'^https?://(dx\.)?doi\.org/', '', candidate_doi, flags=re.I)
                clean_doi_key = re.sub(r'^doi:\s*', '', clean_doi_key, flags=re.I).strip()
                block_full_text = " ".join(bp.text for bp in b.paragraphs)
                if clean_doi_key and clean_doi_key.lower() not in block_full_text.lower():
                    recovered_doi = f"https://doi.org/{clean_doi_key}" if not candidate_doi.startswith("http") else candidate_doi

            if track_changes and tracker:
                if old_n != new_n:
                    replaced = False
                    # Locate the leading run that begins with old_prefix
                    leading_run = None
                    for r in p.runs:
                        if r.text and r.text.strip():
                            leading_run = r
                            break

                    if leading_run is not None:
                        l_txt = leading_run.text
                        l_stripped = l_txt.lstrip()
                        indent = l_txt[:len(l_txt) - len(l_stripped)]
                        if l_stripped.startswith(old_prefix):
                            after_prefix = l_stripped[len(old_prefix):]
                            leading_run.text = indent
                            del_el = make_del_element(old_prefix, tracker.next_id(), tracker.author, tracker.date_str, model_run=leading_run)
                            ins_el = make_ins_element(new_prefix, tracker.next_id(), tracker.author, tracker.date_str, model_run=leading_run)
                            leading_run._r.addnext(del_el)
                            del_el.addnext(ins_el)
                            if after_prefix:
                                ins_el.addnext(make_text_run(leading_run, after_prefix))
                            replaced = True

                    if not replaced and p.runs:
                        # Fallback: strict schema-compliant insertion after <w:pPr>
                        del_el = make_del_element(f"{old_n}. ", tracker.next_id(), tracker.author, tracker.date_str)
                        ins_el = make_ins_element(f"{new_n}. ", tracker.next_id(), tracker.author, tracker.date_str)
                        pPr = p._p.find(qn('w:pPr'))
                        if pPr is not None:
                            pPr.addnext(ins_el)
                            pPr.addnext(del_el)
                        else:
                            p._p.insert(0, ins_el)
                            p._p.insert(0, del_el)
                        p.runs[0].text = rest_content

                if recovered_doi:
                    ins_doi = make_ins_element(f" {recovered_doi}", tracker.next_id(), tracker.author, tracker.date_str)
                    last_p = b.paragraphs[-1]._p
                    sect_pr = last_p.find(qn('w:sectPr'))
                    if sect_pr is not None:
                        sect_pr.addprevious(ins_doi)
                    else:
                        last_p.append(ins_doi)
            else:
                if old_n != new_n:
                    replaced = False
                    leading_run = None
                    for r in p.runs:
                        if r.text and r.text.strip():
                            leading_run = r
                            break

                    if leading_run is not None:
                        l_txt = leading_run.text
                        l_stripped = l_txt.lstrip()
                        indent = l_txt[:len(l_txt) - len(l_stripped)]
                        if l_stripped.startswith(old_prefix):
                            after_prefix = l_stripped[len(old_prefix):]
                            leading_run.text = indent + new_prefix + after_prefix
                            replaced = True

                    if not replaced and p.runs:
                        p.runs[0].text = f"{new_n}. " + rest_content
                        for r in p.runs[1:]:
                            r.text = ""

                if recovered_doi:
                    b.paragraphs[-1].add_run(f" {recovered_doi}")

        # Re-order the atomic reference blocks in the document XML according to new_n
        if renumber_ama and len(blocks) > 1:
            sorted_blocks = sorted(blocks, key=lambda item: item.new_n)
            # Find the anchor element immediately preceding the reference section
            if header_idx is not None and header_idx < len(doc.paragraphs):
                anchor_el = doc.paragraphs[header_idx]._p
            else:
                anchor_el = blocks[0].paragraphs[0]._p.getprevious()

            if anchor_el is not None:
                curr_anchor = anchor_el
                for b in sorted_blocks:
                    for bp in b.paragraphs:
                        curr_anchor.addnext(bp._p)
                        curr_anchor = bp._p
            else:
                parent = blocks[0].paragraphs[0]._p.getparent()
                if parent is not None:
                    for idx, b in enumerate(sorted_blocks):
                        for sub_idx, bp in enumerate(b.paragraphs):
                            parent.insert(idx + sub_idx, bp._p)

        # Inject authentic multi-paragraph bibliography field enclosing all reference blocks
        # Active in BOTH clean mode and track_changes mode
        last_ref_para = None
        if renumber_ama and len(blocks) > 1:
            last_ref_para = sorted_blocks[-1].paragraphs[-1]
        elif blocks:
            last_ref_para = blocks[-1].paragraphs[-1]

        if header_idx is not None and header_idx < len(doc.paragraphs):
            inject_bibliography_field(doc, doc.paragraphs[header_idx], last_para=last_ref_para)
        elif blocks:
            inject_bibliography_field(doc, blocks[0].primary_para, last_para=last_ref_para)

    # Append Co-Scientist Reference Audit & Reachability Ledger
    if include_audit_ledger and references:
        append_audit_ledger_to_docx(doc, references, verdicts, mappings, mapping)

    # Inject AMA doc prefs
    inject_doc_prefs(doc, DEFAULT_STYLE, DEFAULT_STYLE_NAME, library_id=1)

    target = output_target or BytesIO()
    doc.save(target)
    return target

