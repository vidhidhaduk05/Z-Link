"""
Manuscript and Reference Parser for Docx and Plain Text.
"""
import re
from typing import List, Tuple, Optional
import docx
from docx.oxml.ns import qn
from server.models import CitationSite, ReferenceEntry

PAREN_CIT = re.compile(r'\(((?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?)(?:\s*,\s*(?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?))*)\)')
SUP_CIT = re.compile(r'^\d{1,3}(?:[,-]\d{1,3})*$')
REF_START = re.compile(r'^(\d{1,3})\.\s+(.*)$')
REF_HEADER = re.compile(r'^(REFERENCES|Reference List|Bibliography|Works Cited)\s*$', re.I)
BODY_START = re.compile(r'^(ABSTRACT|SUMMARY STATEMENT|INTRODUCTION|Introduction|BACKGROUND|Key Results)\s*$', re.I)

EXPONENT_PREV = set('RrχτIβ')
DOI_RE = re.compile(r'(?:https?://(?:dx\.)?doi\.org/|doi:\s*)(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)', re.I)
FALLBACK_DOI_RE = re.compile(r'\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b')
PMID_RE = re.compile(r'(?:PMID:\s*|pmid:\s*)(\d{6,9})', re.I)

def is_superscript(run) -> bool:
    rPr = run._r.find(qn('w:rPr'))
    if rPr is None:
        return False
    va = rPr.find(qn('w:vertAlign'))
    return va is not None and va.get(qn('w:val')) == 'superscript'

def clean_doi(raw: str) -> str:
    if not raw:
        return ""
    d = raw.strip()
    m = DOI_RE.search(d)
    if m:
        return m.group(1).rstrip('.,;)')
    m2 = FALLBACK_DOI_RE.search(d)
    if m2:
        return m2.group(1).rstrip('.,;)')
    return ""

def parse_reference_line(num: int, line: str) -> ReferenceEntry:
    clean_line = line.strip()
    doi = clean_doi(clean_line)
    pmid_m = PMID_RE.search(clean_line)
    pmid = pmid_m.group(1) if pmid_m else ""
    
    # Try parsing typical biomedical reference format:
    # 1. Author A, Author B. Title of article. Journal Name. 2020;35(2):123-130. doi:10...
    authors = []
    title = ""
    journal = ""
    year = ""
    volume = ""
    issue = ""
    pages = ""

    parts = [p.strip() for p in clean_line.split('. ') if p.strip()]
    if len(parts) >= 2:
        # First part often authors
        author_str = parts[0]
        authors = [a.strip() for a in re.split(r',| and ', author_str) if a.strip()]
        title = parts[1]
    
    # Year/Vol/Issue/Pages pattern: 2021;301(2):392-401 or 2020; 35(4): 200-205 or (2020)
    vol_m = re.search(r'\b(19\d\d|20\d\d)\s*;\s*(\d+)(?:\s*\(([^)]+)\))?\s*:\s*([0-9eE\-–]+)', clean_line)
    if vol_m:
        year = vol_m.group(1)
        volume = vol_m.group(2)
        issue = vol_m.group(3) or ""
        pages = vol_m.group(4)
    else:
        year_m = re.search(r'\b(19\d\d|20\d\d)\b', clean_line)
        if year_m:
            year = year_m.group(1)

    return ReferenceEntry(
        ref_num=num,
        raw_text=clean_line,
        title=title,
        authors=authors,
        journal=journal,
        year=year,
        volume=volume,
        issue=issue,
        pages=pages,
        doi=doi,
        pmid=pmid
    )

def extract_surrounding_sentence(para_text: str, match_start: int, match_end: int) -> str:
    # Split para into sentences approximately
    sentences = re.split(r'(?<=[.!?])\s+', para_text)
    cur_pos = 0
    for s in sentences:
        s_start = cur_pos
        s_end = cur_pos + len(s)
        if s_start <= match_start <= s_end:
            return s.strip()
        cur_pos = s_end + 1
    return para_text[:120].strip()

def parse_docx_manuscript(docx_path: str) -> Tuple[List[str], List[CitationSite], List[ReferenceEntry]]:
    doc = docx.Document(docx_path)
    paras = doc.paragraphs
    return parse_paragraphs_list([p.text for p in paras], doc)

def parse_paragraphs_list(
    para_texts: List[str],
    doc: Optional[docx.Document] = None
) -> Tuple[List[str], List[CitationSite], List[ReferenceEntry]]:
    # 1. Find reference section
    ref_hdr_idx = None
    for i, t in enumerate(para_texts):
        if REF_HEADER.match(t.strip()):
            ref_hdr_idx = i
            break

    # If no header, scan backwards for sequence of numbered items
    if ref_hdr_idx is None:
        for i, t in enumerate(para_texts):
            if REF_START.match(t.strip()) and (i + 1 < len(para_texts) and REF_START.match(para_texts[i+1].strip())):
                ref_hdr_idx = i
                break

    scan_end = ref_hdr_idx if ref_hdr_idx is not None else len(para_texts)

    # 2. Extract reference entries
    references: List[ReferenceEntry] = []
    if ref_hdr_idx is not None:
        for idx in range(ref_hdr_idx, len(para_texts)):
            line = para_texts[idx].strip()
            m = REF_START.match(line)
            if m:
                r_num = int(m.group(1))
                references.append(parse_reference_line(r_num, m.group(2)))

    n_refs = len(references) if references else 999

    # 3. Find body start
    start_idx = 0
    for i in range(scan_end):
        t = para_texts[i].strip()
        if BODY_START.match(t):
            start_idx = i
            break
        if "Corresponding author" in t or "Correspondence to:" in t:
            start_idx = i + 1
            break

    # 4. Extract citation sites
    sites: List[CitationSite] = []

    for pi in range(start_idx, scan_end):
        p_text = para_texts[pi]
        if not p_text.strip():
            continue

        # If docx is provided, we can inspect run superscript formatting
        if doc is not None and pi < len(doc.paragraphs):
            p_obj = doc.paragraphs[pi]
            combined_prev = ""
            for ri, r in enumerate(p_obj.runs):
                r_txt = r.text or ""
                if is_superscript(r) and SUP_CIT.match(r_txt):
                    nums = [int(x) for x in re.split(r'[,-]', r_txt) if x.isdigit()]
                    prev_char = combined_prev[-1:] if combined_prev else ""
                    # exclude affiliation markers like "MD1"
                    if not prev_char or prev_char.isdigit():
                        combined_prev += r_txt
                        continue
                    # exclude statistical exponents
                    if prev_char in EXPONENT_PREV and r_txt in ('2', '3'):
                        combined_prev += r_txt
                        continue
                    if nums and (n_refs == 999 or max(nums) <= n_refs):
                        # Calculate position roughly
                        m_start = len(combined_prev)
                        sent = extract_surrounding_sentence(p_text, m_start, m_start + len(r_txt))
                        sites.append(CitationSite(
                            paragraph_idx=pi,
                            run_idx=ri,
                            kind="sup",
                            text=r_txt,
                            context_before=combined_prev[-40:],
                            sentence=sent,
                            nums=sorted(set(nums)),
                            match_start=m_start,
                            match_end=m_start + len(r_txt)
                        ))
                elif PAREN_CIT.search(r_txt):
                    for m in PAREN_CIT.finditer(r_txt):
                        inner = m.group(1).replace('–', '-')
                        nums = []
                        for part in re.split(r'\s*,\s*', inner):
                            if '-' in part:
                                sp = part.split('-')
                                if len(sp) == 2 and sp[0].strip().isdigit() and sp[1].strip().isdigit():
                                    nums.extend(range(int(sp[0]), int(sp[1]) + 1))
                            elif part.strip().isdigit():
                                nums.append(int(part))
                        if nums and (n_refs == 999 or max(nums) <= n_refs):
                            global_start = len(combined_prev) + m.start()
                            sent = extract_surrounding_sentence(p_text, global_start, global_start + len(m.group(0)))
                            sites.append(CitationSite(
                                paragraph_idx=pi,
                                run_idx=ri,
                                kind="paren",
                                text=m.group(0),
                                context_before=p_text[max(0, global_start - 40):global_start],
                                sentence=sent,
                                nums=sorted(set(nums)),
                                match_start=global_start,
                                match_end=global_start + len(m.group(0))
                            ))
                combined_prev += r_txt
        else:
            # Plain text parsing for parentheticals
            for m in PAREN_CIT.finditer(p_text):
                inner = m.group(1).replace('–', '-')
                nums = []
                for part in re.split(r'\s*,\s*', inner):
                    if '-' in part:
                        sp = part.split('-')
                        if len(sp) == 2 and sp[0].strip().isdigit() and sp[1].strip().isdigit():
                            nums.extend(range(int(sp[0]), int(sp[1]) + 1))
                    elif part.strip().isdigit():
                        nums.append(int(part))
                if nums and (n_refs == 999 or max(nums) <= n_refs):
                    sent = extract_surrounding_sentence(p_text, m.start(), m.end())
                    sites.append(CitationSite(
                        paragraph_idx=pi,
                        run_idx=0,
                        kind="paren",
                        text=m.group(0),
                        context_before=p_text[max(0, m.start() - 40):m.start()],
                        sentence=sent,
                        nums=sorted(set(nums)),
                        match_start=m.start(),
                        match_end=m.end()
                    ))

    return para_texts, sites, references
