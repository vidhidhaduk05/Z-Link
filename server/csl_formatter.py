"""
CSL Citation & Bibliography Formatter Engine (Python Backend)
Provides native Zotero-compatible citation style switching across:
- AMA 11th Edition (Superscript, Sequential)
- Vancouver (Square Brackets [1, 2] & Parentheses (1, 2), Sequential)
- IEEE (Bracketed [1], Sequential)
- Nature (Superscript, Author-First Compact)
- APA 7th Edition (Author-Date (Smith et al., 2020), Alphabetical)
- Harvard (Author-Date (Smith & Doe, 2020), Alphabetical)
"""

import re
from typing import List, Dict, Any, Tuple, Optional
from server.models import ReferenceEntry

CSL_STYLES = {
    # --- Major Radiology Journals (RSNA, ASNR, ARRS, ESR, SIR, ACR) ---
    "radiology": {
        "id": "http://www.zotero.org/styles/radiology",
        "name": "Radiology (RSNA)",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },
    "ajnr": {
        "id": "http://www.zotero.org/styles/american-journal-of-neuroradiology",
        "name": "American Journal of Neuroradiology (AJNR)",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },
    "ajr": {
        "id": "http://www.zotero.org/styles/american-journal-of-roentgenology",
        "name": "American Journal of Roentgenology (AJR)",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },
    "european-radiology": {
        "id": "http://www.zotero.org/styles/european-radiology",
        "name": "European Radiology (ESR / Springer)",
        "category": "numeric",
        "in_text_kind": "bracket",
        "sort": "sequential"
    },
    "radiographics": {
        "id": "http://www.zotero.org/styles/radiographics",
        "name": "RadioGraphics (RSNA)",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },
    "jvir": {
        "id": "http://www.zotero.org/styles/journal-of-vascular-and-interventional-radiology",
        "name": "Journal of Vascular and Interventional Radiology (JVIR)",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },
    "jacr": {
        "id": "http://www.zotero.org/styles/journal-of-the-american-college-of-radiology",
        "name": "Journal of the American College of Radiology (JACR)",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },
    "investigative-radiology": {
        "id": "http://www.zotero.org/styles/investigative-radiology",
        "name": "Investigative Radiology (LWW)",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },
    "academic-radiology": {
        "id": "http://www.zotero.org/styles/academic-radiology",
        "name": "Academic Radiology (Elsevier)",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },
    "clinical-radiology": {
        "id": "http://www.zotero.org/styles/clinical-radiology",
        "name": "Clinical Radiology (RCR / Elsevier)",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },
    "korean-journal-of-radiology": {
        "id": "http://www.zotero.org/styles/korean-journal-of-radiology",
        "name": "Korean Journal of Radiology (KJR)",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },
    "cvir": {
        "id": "http://www.zotero.org/styles/cardiovascular-and-interventional-radiology",
        "name": "CardioVascular and Interventional Radiology (CVIR)",
        "category": "numeric",
        "in_text_kind": "bracket",
        "sort": "sequential"
    },
    "pediatric-radiology": {
        "id": "http://www.zotero.org/styles/pediatric-radiology",
        "name": "Pediatric Radiology (Springer)",
        "category": "numeric",
        "in_text_kind": "bracket",
        "sort": "sequential"
    },
    "journal-of-nuclear-medicine": {
        "id": "http://www.zotero.org/styles/journal-of-nuclear-medicine",
        "name": "Journal of Nuclear Medicine (JNM / SNMMI)",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },

    # --- General Medical & Scientific Numeric Styles ---
    "ama": {
        "id": "http://www.zotero.org/styles/american-medical-association",
        "name": "American Medical Association 11th edition",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },
    "vancouver-bracket": {
        "id": "http://www.zotero.org/styles/vancouver",
        "name": "Vancouver (Square Brackets)",
        "category": "numeric",
        "in_text_kind": "bracket",
        "sort": "sequential"
    },
    "vancouver-paren": {
        "id": "http://www.zotero.org/styles/vancouver-brackets-parentheses",
        "name": "Vancouver (Parentheses)",
        "category": "numeric",
        "in_text_kind": "paren",
        "sort": "sequential"
    },
    "ieee": {
        "id": "http://www.zotero.org/styles/ieee",
        "name": "IEEE",
        "category": "numeric",
        "in_text_kind": "bracket",
        "sort": "sequential"
    },
    "nature": {
        "id": "http://www.zotero.org/styles/nature",
        "name": "Nature",
        "category": "numeric",
        "in_text_kind": "sup",
        "sort": "sequential"
    },

    # --- Author-Date Styles ---
    "apa-7th": {
        "id": "http://www.zotero.org/styles/apa",
        "name": "American Psychological Association 7th edition",
        "category": "author-date",
        "in_text_kind": "author-date",
        "sort": "alphabetical"
    },
    "harvard": {
        "id": "http://www.zotero.org/styles/harvard-cite-them-right",
        "name": "Harvard (Cite Them Right)",
        "category": "author-date",
        "in_text_kind": "author-date",
        "sort": "alphabetical"
    }
}

def parse_author_names(authors_input: Any) -> List[Dict[str, str]]:
    if not authors_input:
        return []
    if isinstance(authors_input, list):
        author_list = authors_input
    else:
        author_list = re.split(r'\s*,\s*|\s+and\s+', str(authors_input))

    PARTICLES = {'van', 'von', 'de', 'del', 'da', 'di', 'du', 'la', 'le', 'der', 'den', 'ter', 'mc', 'mac'}
    parsed = []
    for raw in author_list:
        clean = (raw or "").strip().rstrip(".,;")
        if not clean or clean.lower() == "et al":
            continue
        if "," in clean:
            parts = clean.split(",", 1)
            parsed.append({
                "family": parts[0].strip(),
                "given": parts[1].strip() if len(parts) > 1 else ""
            })
            continue

        parts = clean.split()
        if len(parts) == 1:
            parsed.append({"family": parts[0], "given": ""})
            continue

        p_idx = 0
        while p_idx < len(parts) - 1 and parts[p_idx].lower() in PARTICLES:
            p_idx += 1

        family_words = parts[:p_idx + 1]
        given_words = parts[p_idx + 1:]

        if given_words:
            parsed.append({
                "family": " ".join(family_words),
                "given": " ".join(given_words)
            })
        else:
            parsed.append({
                "family": family_words[0],
                "given": " ".join(family_words[1:])
            })
    return parsed

def condense_numeric_ranges(nums: List[int]) -> str:
    if not nums:
        return ""
    unique = sorted(set(int(n) for n in nums))
    if not unique:
        return ""

    ranges = []
    start = unique[0]
    prev = start

    for cur in unique[1:]:
        if cur == prev + 1:
            prev = cur
        else:
            if start == prev:
                ranges.append(str(start))
            elif prev == start + 1:
                ranges.append(f"{start},{prev}")
            else:
                ranges.append(f"{start}-{prev}")
            start = cur
            prev = cur

    if start == prev:
        ranges.append(str(start))
    elif prev == start + 1:
        ranges.append(f"{start},{prev}")
    else:
        ranges.append(f"{start}-{prev}")

    return ",".join(ranges)

def format_ieee_in_text(nums: List[int]) -> str:
    if not nums:
        return ""
    unique = sorted(set(int(n) for n in nums))
    if not unique:
        return ""

    parts = []
    start = unique[0]
    prev = start

    for cur in unique[1:]:
        if cur == prev + 1:
            prev = cur
        else:
            if start == prev:
                parts.append(f"[{start}]")
            elif prev == start + 1:
                parts.append(f"[{start}], [{prev}]")
            else:
                parts.append(f"[{start}]–[{prev}]")
            start = cur
            prev = cur

    if start == prev:
        parts.append(f"[{start}]")
    elif prev == start + 1:
        parts.append(f"[{start}], [{prev}]")
    else:
        parts.append(f"[{start}]–[{prev}]")

    return ", ".join(parts)

def format_author_date_citation(refs_list: List[ReferenceEntry], style_key: str = "apa-7th") -> str:
    if not refs_list:
        return ""

    citation_strings = []
    for ref in refs_list:
        authors = parse_author_names(ref.authors)
        if len(authors) == 1:
            author_str = authors[0]["family"]
        elif len(authors) == 2:
            sep = " & " if style_key == "apa-7th" else " and "
            author_str = f"{authors[0]['family']}{sep}{authors[1]['family']}"
        elif len(authors) >= 3:
            author_str = f"{authors[0]['family']} et al."
        else:
            author_str = "Anonymous"

        year_m = re.search(r'\b(19\d\d|20\d\d)\b', ref.year or ref.raw_text)
        year_str = year_m.group(1) if year_m else "n.d."
        citation_strings.append(f"{author_str}, {year_str}")

    return f"({'; '.join(citation_strings)})"

def format_in_text_for_style(target_style_key: str, nums: List[int], refs_list: List[ReferenceEntry]) -> Dict[str, Any]:
    style = CSL_STYLES.get(target_style_key, CSL_STYLES["ama"])

    if style["category"] == "author-date":
        return {
            "text": format_author_date_citation(refs_list, target_style_key),
            "is_superscript": False,
            "kind": "author-date"
        }

    if target_style_key == "ieee":
        return {
            "text": format_ieee_in_text(nums),
            "is_superscript": False,
            "kind": "bracket"
        }

    if style.get("in_text_kind") == "bracket" or target_style_key == "vancouver-bracket":
        return {
            "text": f"[{condense_numeric_ranges(nums)}]",
            "is_superscript": False,
            "kind": "bracket"
        }

    if style.get("in_text_kind") == "paren" or target_style_key == "vancouver-paren":
        return {
            "text": f"({condense_numeric_ranges(nums)})",
            "is_superscript": False,
            "kind": "paren"
        }

    # Default: AMA / Nature
    return {
        "text": condense_numeric_ranges(nums),
        "is_superscript": True,
        "kind": "sup"
    }

def format_bibliography_entry_ama(num: int, ref: ReferenceEntry) -> str:
    authors = parse_author_names(ref.authors)
    author_str = ""
    if authors:
        if len(authors) <= 6:
            author_str = ", ".join(f"{a['family']} {a['given']}".strip() for a in authors)
        else:
            author_str = ", ".join(f"{a['family']} {a['given']}".strip() for a in authors[:3]) + ", et al"

    title_str = (ref.title or "").strip()
    if title_str and not title_str.endswith("."):
        title_str += "."

    journal_str = (ref.journal or "").strip()
    pub_str = ""
    if ref.year:
        pub_str += ref.year
    if ref.volume:
        pub_str += f";{ref.volume}"
        if ref.issue:
            pub_str += f"({ref.issue})"
    if ref.pages:
        pub_str += f":{ref.pages}"
    if pub_str and not pub_str.endswith("."):
        pub_str += "."

    doi_str = f"doi:{ref.doi}" if ref.doi else ""

    segments = [s for s in [author_str, title_str, f"{journal_str}. {pub_str}" if (journal_str and pub_str) else (journal_str or pub_str), doi_str] if s]
    if not segments:
        return f"{num}. {ref.raw_text}"
    return f"{num}. {' '.join(segments)}"

def format_bibliography_entry_vancouver(num: int, ref: ReferenceEntry) -> str:
    authors = parse_author_names(ref.authors)
    author_str = ""
    if authors:
        if len(authors) <= 6:
            author_str = ", ".join(f"{a['family']} {a['given']}".strip() for a in authors)
        else:
            author_str = ", ".join(f"{a['family']} {a['given']}".strip() for a in authors[:6]) + ", et al."

    title_str = (ref.title or "").strip()
    if title_str and not title_str.endswith("."):
        title_str += "."

    journal_str = (ref.journal or "").strip()
    pub_str = ""
    if ref.year:
        pub_str += ref.year
    if ref.volume:
        pub_str += f";{ref.volume}"
        if ref.issue:
            pub_str += f"({ref.issue})"
    if ref.pages:
        pub_str += f":{ref.pages}"
    if pub_str and not pub_str.endswith("."):
        pub_str += "."

    doi_str = f"Available from: https://doi.org/{ref.doi}" if ref.doi else ""

    segments = [s for s in [author_str, title_str, f"{journal_str}. {pub_str}" if (journal_str and pub_str) else (journal_str or pub_str), doi_str] if s]
    if not segments:
        return f"{num}. {ref.raw_text}"
    return f"{num}. {' '.join(segments)}"

def format_bibliography_entry_apa7(ref: ReferenceEntry) -> str:
    authors = parse_author_names(ref.authors)
    author_str = ""
    if len(authors) == 1:
        g = authors[0]['given'][:1] + "." if authors[0]['given'] else ""
        author_str = f"{authors[0]['family']}, {g}".strip()
    elif len(authors) == 2:
        g1 = authors[0]['given'][:1] + "." if authors[0]['given'] else ""
        g2 = authors[1]['given'][:1] + "." if authors[1]['given'] else ""
        author_str = f"{authors[0]['family']}, {g1}, & {authors[1]['family']}, {g2}".strip()
    elif len(authors) > 2:
        firsts = [f"{a['family']}, {a['given'][:1] + '.' if a['given'] else ''}".strip() for a in authors[:19]]
        if len(authors) > 20:
            last = authors[-1]
            gl = last['given'][:1] + "." if last['given'] else ""
            author_str = f"{', '.join(firsts)}, ... {last['family']}, {gl}".strip()
        else:
            last = authors[-1]
            gl = last['given'][:1] + "." if last['given'] else ""
            author_str = f"{', '.join(firsts[:-1])}, & {last['family']}, {gl}".strip()

    year_str = f"({ref.year})." if ref.year else "(n.d.)."
    title_str = (ref.title or "").strip()
    if title_str and not title_str.endswith("."):
        title_str += "."

    journal_str = (ref.journal or "").strip()
    vol_str = ""
    if ref.volume:
        vol_str += ref.volume
        if ref.issue:
            vol_str += f"({ref.issue})"
    if ref.pages:
        vol_str += f", {ref.pages}." if vol_str else f"{ref.pages}."
    elif vol_str:
        vol_str += "."

    doi_str = f"https://doi.org/{ref.doi}" if ref.doi else ""

    segments = [s for s in [author_str, year_str, title_str, f"{journal_str}, {vol_str}" if (journal_str and vol_str) else (journal_str or vol_str), doi_str] if s]
    if not segments:
        return ref.raw_text
    return " ".join(segments)

def format_bibliography_entry_ieee(num: int, ref: ReferenceEntry) -> str:
    authors = parse_author_names(ref.authors)
    author_str = ""
    if len(authors) == 1:
        g = authors[0]['given'] + " " if authors[0]['given'] else ""
        author_str = f"{g}{authors[0]['family']}"
    elif len(authors) == 2:
        g1 = authors[0]['given'] + " " if authors[0]['given'] else ""
        g2 = authors[1]['given'] + " " if authors[1]['given'] else ""
        author_str = f"{g1}{authors[0]['family']} and {g2}{authors[1]['family']}"
    elif len(authors) > 2:
        g1 = authors[0]['given'] + " " if authors[0]['given'] else ""
        author_str = f"{g1}{authors[0]['family']} et al."

    title_str = f'"{ref.title.strip()},"' if ref.title else ""
    details = []
    if ref.journal:
        details.append(ref.journal.strip())
    if ref.volume:
        details.append(f"vol. {ref.volume}")
    if ref.issue:
        details.append(f"no. {ref.issue}")
    if ref.pages:
        details.append(f"pp. {ref.pages}")
    if ref.year:
        details.append(ref.year)

    details_str = ", ".join(details)
    if details_str and not details_str.endswith("."):
        details_str += "."

    doi_str = f"doi: {ref.doi}." if ref.doi else ""

    segments = [s for s in [f"{author_str}," if author_str else "", title_str, details_str, doi_str] if s]
    if not segments:
        return f"[{num}] {ref.raw_text}"
    return f"[{num}] {' '.join(segments)}"

def format_bibliography_for_style(target_style_key: str, num: int, ref: ReferenceEntry) -> str:
    if target_style_key in ("apa-7th", "harvard"):
        return format_bibliography_entry_apa7(ref)
    if target_style_key in ("vancouver-bracket", "vancouver-paren", "european-radiology", "cvir", "pediatric-radiology"):
        return format_bibliography_entry_vancouver(num, ref)
    if target_style_key == "ieee":
        return format_bibliography_entry_ieee(num, ref)
    if target_style_key == "nature":
        return format_bibliography_entry_nature(num, ref)
    return format_bibliography_entry_ama(num, ref)

def sort_references_for_style(
    target_style_key: str,
    references: List[ReferenceEntry],
    citation_order_map: Dict[int, int]
) -> List[ReferenceEntry]:
    style = CSL_STYLES.get(target_style_key, CSL_STYLES["ama"])

    if style["sort"] == "alphabetical":
        def sort_key(r: ReferenceEntry):
            parsed = parse_author_names(r.authors)
            family = parsed[0]["family"].lower() if parsed else r.raw_text.lower()
            year = int(r.year) if r.year and r.year.isdigit() else 0
            return (family, year, (r.title or "").lower())
        return sorted(references, key=sort_key)

    # Numeric styles: sequential by order of appearance
    def num_sort_key(r: ReferenceEntry):
        order = citation_order_map.get(r.ref_num, 999999)
        return (order, r.ref_num)
    return sorted(references, key=num_sort_key)
