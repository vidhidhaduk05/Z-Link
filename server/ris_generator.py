"""
Standards-compliant RIS File Generator.
"""
from typing import List, Dict
from server.models import ReferenceEntry, ValidationVerdict

def generate_ris(
    references: List[ReferenceEntry],
    verdicts: Dict[int, ValidationVerdict] = None,
    mapping: Dict[int, int] = None
) -> str:
    """
    Format reference records as standard RIS for Zotero/EndNote import.
    When mapping is provided, references are ordered and labeled by their new AMA sequential numbers.
    """
    sorted_refs = references
    if mapping:
        sorted_refs = sorted(references, key=lambda r: mapping.get(r.ref_num, r.ref_num))

    lines = []
    for ref in sorted_refs:
        v = (verdicts or {}).get(ref.ref_num)
        new_num = mapping.get(ref.ref_num, ref.ref_num) if mapping else ref.ref_num
        
        # Merge best metadata (Crossref preferred if available)
        title = (v.crossref_title if v and v.crossref_title else ref.title) or "Untitled Document"
        authors = (v.crossref_authors if v and v.crossref_authors else ref.authors) or ["Unknown Author"]
        journal = (v.crossref_journal if v and v.crossref_journal else ref.journal) or ""
        year = (v.crossref_year if v and v.crossref_year else ref.year) or ""
        volume = (v.crossref_volume if v and v.crossref_volume else ref.volume) or ""
        issue = (v.crossref_issue if v and v.crossref_issue else ref.issue) or ""
        pages = (v.crossref_pages if v and v.crossref_pages else ref.pages) or ""
        doi = ref.doi or ""

        lines.append("TY  - JOUR")
        lines.append(f"ID  - ITEM-{new_num}")
        lines.append(f"M1  - Ref {new_num}")
        for a in authors:
            lines.append(f"AU  - {a}")
        lines.append(f"TI  - {title}")
        if journal:
            lines.append(f"JO  - {journal}")
            lines.append(f"TA  - {journal}")
        if year:
            lines.append(f"PY  - {year}")
        if volume:
            lines.append(f"VL  - {volume}")
        if issue:
            lines.append(f"IS  - {issue}")
        if pages:
            lines.append(f"SP  - {pages}")
        if doi:
            lines.append(f"DO  - {doi}")
            lines.append(f"UR  - https://doi.org/{doi}")
        lines.append("ER  - ")
        lines.append("")

    return "\n".join(lines)

