"""
Standards-compliant RIS File Generator.
"""
from typing import List, Dict
from server.models import ReferenceEntry, ValidationVerdict

def generate_ris(references: List[ReferenceEntry], verdicts: Dict[int, ValidationVerdict] = None) -> str:
    """
    Format reference records as standard RIS for Zotero/EndNote import.
    """
    lines = []
    for ref in references:
        v = (verdicts or {}).get(ref.ref_num)
        
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
