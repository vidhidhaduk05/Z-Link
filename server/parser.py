"""
Manuscript and Reference Parser for Docx and Plain Text.
"""
import re
from typing import List, Tuple, Optional
import docx
from docx.oxml.ns import qn
from server.models import CitationSite, ReferenceEntry

PAREN_CIT = re.compile(r'\(((?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?)(?:\s*,\s*(?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?))*)\)')
BRACKET_CIT = re.compile(r'\[((?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?)(?:\s*,\s*(?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?))*)]')
PUNCT_CIT = re.compile(r'(?<=[.,;:])((?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?)(?:\s*,\s*(?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?))*)')
SUP_CIT = re.compile(r'^\d{1,3}(?:[,-]\d{1,3})*$')
REF_START = re.compile(r'^(\d{1,3})\.\s+(.*)$')
REF_HEADER = re.compile(r'^(REFERENCES|Reference List|Bibliography|Works Cited)\s*$', re.I)
BODY_START = re.compile(r'^(ABSTRACT|SUMMARY STATEMENT|INTRODUCTION|Introduction|BACKGROUND|Key Results)\s*$', re.I)
POST_REF_HEADER = re.compile(
    r'^(Supplementary\s+|Supplemental\s+|Appendix\b|Appendices\b|Tables?\b|Figure\s+Legends?|Figures?\b|Author\s+Contributions|Funding\b|Conflict(?:s)?\s+of\s+Interest|IRB\s+Statement|Informed\s+Consent)',
    re.I
)
YEAR_RE = re.compile(r'\b(19\d\d|20\d\d)\b')

EXPONENT_PREV_CHARS = set('RrχτIβtfzp')
EXPONENT_PREV_WORDS = ('cm', 'mm', 'nm', 'um', 'µm', 'km', 'm', 'kg', 'mg', 'g', 'ml', 'dl', 'mol', 'chi', 'tau', 'beta', 'st', 'nd', 'rd', 'th')

# Clinical & statistical units that precede non-citation parentheticals/brackets
NON_CITATION_PRECEDING_WORDS = re.compile(
    r'\b('
    # Patient & clinical counts (plural)
    r'patients|cases|cohorts|subjects|participants|controls|individuals|'
    r'males|females|men|women|children|adults|infants|volunteers|records|'
    # Temporal & age nouns (plural, or age)
    r'years|year-old|aged?|months|weeks|days|hours|y/o|yo|'
    # Statistical measures & clinical counts
    r'n|N|IQR|range|mean|median|SD|SEM|CI|total|subgroups?|proportions?|rates?|counts?|'
    # Classification, tables, figures, formulas, and dosage units
    r'dose|doses|mg|g|ml|mcg|table|fig|figure|equation|eq|formula|model|item|point|rule|part|grade|stage|type|class|step'
    r')\s*$',
    re.I
)
CLASSIFICATION_NOUNS = NON_CITATION_PRECEDING_WORDS

CLINICAL_SCALE_RE = re.compile(
    r'\b(graded\s+(?:on|as|by)?|scores?|scales?|grades?|grading|stages?|staging|classes?|indices?|index|points?|severity|levels?|subscores?|criteria|systems?|angiography|perfusion|tomography|mRS|NIHSS|GCS|mTICI|TICI|TIMI|ASPECTS|DSA)\b',
    re.I
)
ENUMERATED_LIST_START = re.compile(r'^\s*\((?:\d{1,2})\)\s+[A-Za-z]')

# Content inside parens/brackets that indicates clinical counts/percentages/ranges, not citation numbers
NON_CITATION_INNER_CONTENT = re.compile(
    r'(?:'
    r'%\s*$|'                         # e.g. (63.3%)
    r'\b(?:IQR|range|mean|median|SD|SEM|CI|vs|versus)\b|'  # e.g. (IQR, 3.9-14.5)
    r'^[nN]\s*=\s*\d+|'               # e.g. (n = 45)
    r'\b\d+\s*patients?\b|'           # e.g. (45 patients)
    r'^\d+\s*,\s*\d+(?:\.\d+)?\s*%|'   # e.g. (38, 63.3%)
    r'^(?:19\d\d|20\d\d)(?:\s*[-–]\s*(?:19\d\d|20\d\d))?$' # e.g. (2018-2022) or (2020)
    r')',
    re.I
)

# Clinical statement markers in numbered sentences (e.g. "1. 45 patients were enrolled in 2020")
CLINICAL_STATEMENT_RE = re.compile(
    r'\b('
    r'patients?|cases?|cohorts?|subjects?|participants?|controls?|individuals?|'
    r'were\s+enrolled|underwent|were\s+treated|were\s+evaluated|were\s+included|were\s+admitted|'
    r'mean\s+age|median\s+age|years?\s+old|inclusion\s+criteria|exclusion\s+criteria|'
    r'follow-up|in\s+our\s+study|in\s+this\s+study|our\s+cohort|adverse\s+events?|'
    r'hazard\s+ratio|odds\s+ratio|confidence\s+interval|p\s*[<=]\s*0?\.\d+'
    r')\b',
    re.I
)

BIBLIO_JOURNAL_PAGINATION_RE = re.compile(r'\b(19\d\d|20\d\d)\s*;\s*\d+(?:\s*\([^)]+\))?\s*:\s*[0-9eE\-–]+')
BIBLIO_CONTAINERS_RE = re.compile(
    r'\b('
    r'et\s+al|doi:|https?://|PMID:|vol\.|volume|issue|pp\.|pages|'
    r'press|publisher|springer|elsevier|wiley|oxford|cambridge|academic\s+press|'
    r'in:\s+[A-Z][a-z]+'
    r')\b',
    re.I
)

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

def is_authentic_bibliographic_reference(line: str) -> bool:
    """
    Discriminates an authentic bibliographic reference from clinical study statements,
    patient counts, or section headers that contain numbers/years.
    """
    clean = line.strip()
    if not clean:
        return False
    # Definite bibliographic identifiers
    if DOI_RE.search(clean) or FALLBACK_DOI_RE.search(clean) or PMID_RE.search(clean):
        return True
    # Explicit journal volume/issue pagination (e.g. 2020;35(2):123-130)
    if BIBLIO_JOURNAL_PAGINATION_RE.search(clean):
        return True
    # Clinical study statements talking about patients/enrolled/follow-up/IQR are NOT references
    if CLINICAL_STATEMENT_RE.search(clean):
        return False
    # If it contains a publication year (19xx or 20xx)
    if YEAR_RE.search(clean):
        return True
    # Typical bibliographic delimiters: semicolons, colons, or 'et al'
    if 'et al' in clean.lower() or ';' in clean or ':' in clean:
        return True
    words = clean.split()
    if len(words) <= 4:
        return False
    return True

def is_likely_reference_line(line: str) -> bool:
    """Ensure candidate reference line is an authentic bibliographic entry and not a clinical statement or heading."""
    return is_authentic_bibliographic_reference(line)

def profile_document_citation_format(
    para_texts: List[str],
    doc: Optional[docx.Document] = None,
    scan_end: int = 0
) -> str:
    """
    Pass 1: Profile manuscript citation format across body paragraphs.
    Counts superscript runs, square brackets [1, 2], and sentence parens (1, 2).
    Returns dominant style: 'sup', 'bracket', or 'paren' (or 'mixed' if both sup & paren are prominent).
    """
    sup_count = 0
    bracket_count = 0
    paren_count = 0

    if doc is not None:
        for pi in range(min(scan_end, len(doc.paragraphs))):
            p_obj = doc.paragraphs[pi]
            combined = ""
            active_runs = [docx.text.run.Run(r_el, p_obj) for r_el in p_obj._p.xpath('.//w:r[not(ancestor::w:del)]')]
            for r in active_runs:
                r_txt = r.text or ""
                if is_superscript(r) and SUP_CIT.match(r_txt):
                    prev_char = combined[-1:] if combined else ""
                    if prev_char and not prev_char.isdigit():
                        if not (prev_char in EXPONENT_PREV_CHARS and r_txt in ('2', '3', '4')) and not any(combined.rstrip().lower().endswith(w) for w in EXPONENT_PREV_WORDS):
                            sup_count += 1
                combined += r_txt

    for pi in range(min(scan_end, len(para_texts))):
        p_text = para_texts[pi]
        if not p_text.strip():
            continue
        # Brackets
        for m in BRACKET_CIT.finditer(p_text):
            prior = p_text[:m.start()].rstrip()
            if NON_CITATION_PRECEDING_WORDS.search(prior) or CLINICAL_SCALE_RE.search(prior[-60:]):
                continue
            if NON_CITATION_INNER_CONTENT.search(m.group(0)[1:-1]):
                continue
            inner = m.group(1).replace('–', '-')
            parts = [p.strip() for p in re.split(r'\s*,\s*', inner) if p.strip()]
            if parts and all(re.match(r'^\d{1,3}(?:-\d{1,3})?$', pt) for pt in parts):
                if any(int(pt.split('-')[0]) >= 1900 for pt in parts):
                    continue
                bracket_count += 1
        # Parens (applying clinical scale guards)
        for m in PAREN_CIT.finditer(p_text):
            prior = p_text[:m.start()].rstrip()
            if NON_CITATION_PRECEDING_WORDS.search(prior) or CLINICAL_SCALE_RE.search(prior[-60:]):
                continue
            if NON_CITATION_INNER_CONTENT.search(m.group(0)[1:-1]):
                continue
            inner = m.group(1).replace('–', '-')
            parts = [p.strip() for p in re.split(r'\s*,\s*', inner) if p.strip()]
            if parts and all(re.match(r'^\d{1,3}(?:-\d{1,3})?$', pt) for pt in parts):
                if any(int(pt.split('-')[0]) >= 1900 for pt in parts):
                    continue
                paren_count += 1

    # Dominant format determination
    if sup_count >= 3 and sup_count >= bracket_count and (paren_count == 0 or sup_count >= 2 * paren_count):
        return "sup"
    if bracket_count >= 3 and bracket_count >= paren_count:
        return "bracket"
    if paren_count >= 3 and sup_count == 0 and bracket_count == 0:
        return "paren"
    if sup_count >= 2 and paren_count >= 2:
        return "mixed"
    if sup_count > 0:
        return "sup"
    if bracket_count > 0:
        return "bracket"
    if paren_count > 0:
        return "paren"
    return "sup"

def has_tracked_revisions(doc: docx.Document) -> bool:
    """Returns True if the document contains any OpenXML <w:del> or <w:ins> elements."""
    body = doc._body._element
    return bool(body.xpath('.//w:del') or body.xpath('.//w:ins'))

def accept_prior_revisions(doc: docx.Document) -> int:
    """
    Optional helper: Accepts all existing tracked revisions in doc, bringing it to the
    'Final (Accepted)' baseline before citation auditing and linking.
    - Removes all <w:del> elements completely.
    - Unwraps all <w:ins> elements so their child runs become normal runs.
    Returns the count of resolved revisions.
    """
    body = doc._body._element
    dels = body.xpath('.//w:del')
    inss = body.xpath('.//w:ins')
    total = len(dels) + len(inss)

    for del_el in dels:
        parent = del_el.getparent()
        if parent is not None:
            parent.remove(del_el)

    for ins_el in inss:
        parent = ins_el.getparent()
        if parent is not None:
            ins_idx = parent.index(ins_el)
            children = list(ins_el)
            for offset, child in enumerate(children):
                parent.insert(ins_idx + offset, child)
            parent.remove(ins_el)

    return total

def parse_docx_manuscript(
    docx_path: str,
    citation_format: str = "auto",
    accept_revisions: bool = False
) -> Tuple[List[str], List[CitationSite], List[ReferenceEntry]]:
    doc = docx.Document(docx_path)
    if accept_revisions and has_tracked_revisions(doc):
        accept_prior_revisions(doc)
    
    # Extract active text per paragraph without modifying or accepting revisions
    para_texts = []
    for p in doc.paragraphs:
        t_nodes = p._p.xpath('.//w:t[not(ancestor::w:del)]/text()')
        para_texts.append("".join(t_nodes))

    return parse_paragraphs_list(para_texts, doc, citation_format=citation_format)

def parse_paragraphs_list(
    para_texts: List[str],
    doc: Optional[docx.Document] = None,
    citation_format: str = "auto"
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
            if REF_START.match(t.strip()) and is_authentic_bibliographic_reference(t.strip()) and (i + 1 < len(para_texts) and REF_START.match(para_texts[i+1].strip()) and is_authentic_bibliographic_reference(para_texts[i+1].strip())):
                ref_hdr_idx = i
                break

    scan_end = ref_hdr_idx if ref_hdr_idx is not None else len(para_texts)

    # 2. Extract reference entries
    references: List[ReferenceEntry] = []
    if ref_hdr_idx is not None:
        for idx in range(ref_hdr_idx, len(para_texts)):
            line = para_texts[idx].strip()
            if not line:
                continue
            # Stop if a post-reference section begins (e.g. Supplementary, Figures, Tables)
            if idx > ref_hdr_idx and POST_REF_HEADER.match(line) and len(references) > 0:
                break
            m = REF_START.match(line)
            if m:
                r_num = int(m.group(1))
                content = m.group(2)
                # Verify it is an authentic bibliographic reference and not a clinical sentence or heading
                if is_authentic_bibliographic_reference(content) or (idx + 1 < len(para_texts) and (REF_START.match(para_texts[idx+1].strip()) and is_authentic_bibliographic_reference(para_texts[idx+1].strip()))):
                    references.append(parse_reference_line(r_num, content))
            elif references:
                # Multi-line reference continuation: check if next paragraph is wrapped DOI / PMID / URL
                if DOI_RE.search(line) or FALLBACK_DOI_RE.search(line) or PMID_RE.search(line):
                    last_ref = references[-1]
                    last_ref.raw_text += " " + line
                    if not last_ref.doi:
                        last_ref.doi = clean_doi(line)
                    if not last_ref.pmid:
                        pm = PMID_RE.search(line)
                        if pm:
                            last_ref.pmid = pm.group(1)

    n_refs = len(references) if references else 999

    # Determine effective citation format via Pass 1 profiling if auto
    effective_format = citation_format
    if citation_format == "auto":
        effective_format = profile_document_citation_format(para_texts, doc, scan_end=scan_end)

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
            active_runs = [docx.text.run.Run(r_el, p_obj) for r_el in p_obj._p.xpath('.//w:r[not(ancestor::w:del)]')]
            for ri, r in enumerate(active_runs):
                r_txt = r.text or ""
                # 1. Superscript check
                if effective_format in ("auto", "sup", "mixed") and is_superscript(r) and SUP_CIT.match(r_txt):
                    inner = r_txt.replace('–', '-')
                    nums = []
                    for part in re.split(r'\s*,\s*', inner):
                        if '-' in part:
                            sp = part.split('-')
                            if len(sp) == 2 and sp[0].strip().isdigit() and sp[1].strip().isdigit():
                                nums.extend(range(int(sp[0]), int(sp[1]) + 1))
                        elif part.strip().isdigit():
                            nums.append(int(part))

                    prev_char = combined_prev[-1:] if combined_prev else ""
                    # exclude affiliation markers like "MD1" or trailing digits
                    if not prev_char or prev_char.isdigit():
                        combined_prev += r_txt
                        continue
                    # exclude statistical exponents and physical units
                    if prev_char in EXPONENT_PREV_CHARS and r_txt in ('2', '3', '4'):
                        combined_prev += r_txt
                        continue
                    if any(combined_prev.rstrip().lower().endswith(w) for w in EXPONENT_PREV_WORDS) and r_txt in ('2', '3', '4'):
                        combined_prev += r_txt
                        continue
                    if any(n >= 1900 for n in nums):
                        combined_prev += r_txt
                        continue
                    if nums and (n_refs == 999 or max(nums) <= n_refs):
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
                
                # 2. Bracket check [1, 2]
                if effective_format in ("auto", "bracket") and BRACKET_CIT.search(r_txt):
                    for m in BRACKET_CIT.finditer(r_txt):
                        context_prior = (combined_prev + r_txt[:m.start()]).rstrip()
                        if NON_CITATION_PRECEDING_WORDS.search(context_prior) or CLINICAL_SCALE_RE.search(context_prior[-60:]):
                            continue
                        if NON_CITATION_INNER_CONTENT.search(m.group(0)[1:-1]):
                            continue
                        inner = m.group(1).replace('–', '-')
                        nums = []
                        for part in re.split(r'\s*,\s*', inner):
                            if '-' in part:
                                sp = part.split('-')
                                if len(sp) == 2 and sp[0].strip().isdigit() and sp[1].strip().isdigit():
                                    nums.extend(range(int(sp[0]), int(sp[1]) + 1))
                            elif part.strip().isdigit():
                                nums.append(int(part))
                        if any(n >= 1900 for n in nums):
                            continue
                        if nums and (n_refs == 999 or max(nums) <= n_refs):
                            global_start = len(combined_prev) + m.start()
                            sent = extract_surrounding_sentence(p_text, global_start, global_start + len(m.group(0)))
                            sites.append(CitationSite(
                                paragraph_idx=pi,
                                run_idx=ri,
                                kind="bracket",
                                text=m.group(0),
                                context_before=p_text[max(0, global_start - 40):global_start],
                                sentence=sent,
                                nums=sorted(set(nums)),
                                match_start=global_start,
                                match_end=global_start + len(m.group(0))
                            ))

                # 3. Parenthetical check (1, 2)
                if effective_format in ("auto", "paren", "mixed") and PAREN_CIT.search(r_txt):
                    for m in PAREN_CIT.finditer(r_txt):
                        # Guard against clinical nouns e.g. "patients (12)", "years (1-5)"
                        context_prior = (combined_prev + r_txt[:m.start()]).rstrip()
                        if NON_CITATION_PRECEDING_WORDS.search(context_prior) or CLINICAL_SCALE_RE.search(context_prior[-60:]):
                            continue
                        if NON_CITATION_INNER_CONTENT.search(m.group(0)[1:-1]):
                            continue
                        # Guard against enumerated lists e.g. "(1) We analyzed..."
                        sentence_start_check = r_txt[m.start():m.end() + 20]
                        if ENUMERATED_LIST_START.match(sentence_start_check) and not context_prior:
                            continue

                        inner = m.group(1).replace('–', '-')
                        nums = []
                        has_zero = False
                        for part in re.split(r'\s*,\s*', inner):
                            if '-' in part:
                                sp = part.split('-')
                                if len(sp) == 2 and sp[0].strip().isdigit() and sp[1].strip().isdigit():
                                    s0, s1 = int(sp[0]), int(sp[1])
                                    if s0 <= 0 or s1 <= 0:
                                        has_zero = True
                                        break
                                    nums.extend(range(s0, s1 + 1))
                            elif part.strip().isdigit():
                                val = int(part)
                                if val <= 0:
                                    has_zero = True
                                    break
                                nums.append(val)
                        if has_zero or not nums:
                            continue
                        if any(n >= 1900 for n in nums):
                            continue
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
            # Plain text parsing
            # 1. Bracket check
            if effective_format in ("auto", "bracket"):
                for m in BRACKET_CIT.finditer(p_text):
                    context_prior = p_text[:m.start()].rstrip()
                    if NON_CITATION_PRECEDING_WORDS.search(context_prior) or CLINICAL_SCALE_RE.search(context_prior[-60:]):
                        continue
                    if NON_CITATION_INNER_CONTENT.search(m.group(0)[1:-1]):
                        continue
                    inner = m.group(1).replace('–', '-')
                    nums = []
                    has_zero = False
                    for part in re.split(r'\s*,\s*', inner):
                        if '-' in part:
                            sp = part.split('-')
                            if len(sp) == 2 and sp[0].strip().isdigit() and sp[1].strip().isdigit():
                                s0, s1 = int(sp[0]), int(sp[1])
                                if s0 <= 0 or s1 <= 0:
                                    has_zero = True
                                    break
                                nums.extend(range(s0, s1 + 1))
                        elif part.strip().isdigit():
                            val = int(part)
                            if val <= 0:
                                has_zero = True
                                break
                            nums.append(val)
                    if has_zero or not nums:
                        continue
                    if any(n >= 1900 for n in nums):
                        continue
                    if nums and (n_refs == 999 or max(nums) <= n_refs):
                        sent = extract_surrounding_sentence(p_text, m.start(), m.end())
                        sites.append(CitationSite(
                            paragraph_idx=pi,
                            run_idx=0,
                            kind="bracket",
                            text=m.group(0),
                            context_before=p_text[max(0, m.start() - 40):m.start()],
                            sentence=sent,
                            nums=sorted(set(nums)),
                            match_start=m.start(),
                            match_end=m.end()
                        ))

            # 2. Parenthetical check
            if effective_format in ("auto", "paren", "mixed"):
                for m in PAREN_CIT.finditer(p_text):
                    context_prior = p_text[:m.start()].rstrip()
                    if NON_CITATION_PRECEDING_WORDS.search(context_prior) or CLINICAL_SCALE_RE.search(context_prior[-60:]):
                        continue
                    if NON_CITATION_INNER_CONTENT.search(m.group(0)[1:-1]):
                        continue
                    trailing = p_text[m.start():m.end() + 20]
                    if ENUMERATED_LIST_START.match(trailing) and not context_prior:
                        continue

                    inner = m.group(1).replace('–', '-')
                    nums = []
                    has_zero = False
                    for part in re.split(r'\s*,\s*', inner):
                        if '-' in part:
                            sp = part.split('-')
                            if len(sp) == 2 and sp[0].strip().isdigit() and sp[1].strip().isdigit():
                                s0, s1 = int(sp[0]), int(sp[1])
                                if s0 <= 0 or s1 <= 0:
                                    has_zero = True
                                    break
                                nums.extend(range(s0, s1 + 1))
                        elif part.strip().isdigit():
                            val = int(part)
                            if val <= 0:
                                has_zero = True
                                break
                            nums.append(val)
                    if has_zero or not nums:
                        continue
                    if any(n >= 1900 for n in nums):
                        continue
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

