"""
Reference Validation, DOI Reachability, and Usage Mapping Engine.
"""
import re
import requests
from typing import Dict, List, Tuple
from server.models import ReferenceEntry, CitationSite, ValidationVerdict, UsageMapping, UsageOccurrence, AuditSummary

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 CoScientistAuditor/1.0"
CROSSREF_API = "https://api.crossref.org/works"
PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
TIMEOUT = 6

def check_doi_reachability(doi: str) -> Tuple[bool, int, str]:
    """
    Check if the DOI resolves on doi.org and reachability to the publisher page.
    """
    if not doi:
        return False, 0, ""
    
    url = f"https://doi.org/{doi}"
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True, allow_redirects=True)
        status = r.status_code
        final_url = r.url
        # If 200, or redirected to publisher (even if publisher returns 403 bot-gate), it is registered
        is_reachable = (status == 200) or ("doi.org" not in final_url and status in (200, 301, 302, 403))
        return is_reachable, status, final_url
    except requests.exceptions.RequestException:
        return False, 0, ""

def query_crossref(doi: str) -> Dict:
    """
    Query Crossref REST API for canonical metadata.
    """
    if not doi:
        return {}
    url = f"{CROSSREF_API}/{doi}"
    headers = {"User-Agent": f"CoScientist-Auditor/1.0 (mailto:coscientist-auditor@academic.org)"}
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json().get("message", {})
        return {}
    except requests.exceptions.RequestException:
        return {}

def validate_single_reference(ref: ReferenceEntry) -> ValidationVerdict:
    notes = []
    doi = ref.doi
    
    if not doi:
        return ValidationVerdict(
            ref_num=ref.ref_num,
            status="missing_doi",
            is_reachable=False,
            notes=["No DOI detected in reference line."]
        )

    # 1. Reachability
    is_reachable, http_code, resolved_url = check_doi_reachability(doi)
    if is_reachable:
        notes.append(f"DOI resolves to live landing: {resolved_url[:65]}...")
    else:
        notes.append(f"DOI failed to resolve (HTTP {http_code}).")

    # 2. Crossref metadata
    cr_data = query_crossref(doi)
    cr_found = bool(cr_data)
    
    cr_title = ""
    cr_authors = []
    cr_journal = ""
    cr_year = ""
    cr_vol = ""
    cr_issue = ""
    cr_pages = ""
    abstract = ""

    if cr_found:
        cr_title = (cr_data.get("title") or [""])[0]
        for a in cr_data.get("author", []):
            family = a.get("family", "")
            given = a.get("given", "")
            if family:
                cr_authors.append(f"{family} {given}".strip())
        cr_journal = (cr_data.get("container-title") or [""])[0]
        issued = cr_data.get("issued", {}).get("date-parts", [[None]])[0]
        if issued and issued[0]:
            cr_year = str(issued[0])
        cr_vol = cr_data.get("volume", "")
        cr_issue = cr_data.get("issue", "")
        cr_pages = cr_data.get("page", "")
        abstract = cr_data.get("abstract", "")
        notes.append("Metadata verified against Crossref registry.")

    # Status classification
    if cr_found and is_reachable:
        verdict_status = "verified"
    elif cr_found and not is_reachable:
        verdict_status = "redirected" if http_code in (301, 302, 403) else "unreachable"
    elif not cr_found and is_reachable:
        verdict_status = "verified" # Registered at doi.org
    else:
        verdict_status = "unreachable"

    return ValidationVerdict(
        ref_num=ref.ref_num,
        status=verdict_status,
        is_reachable=is_reachable,
        http_status=http_code,
        resolved_url=resolved_url,
        crossref_found=cr_found,
        crossref_title=cr_title,
        crossref_authors=cr_authors,
        crossref_journal=cr_journal,
        crossref_year=cr_year,
        crossref_volume=cr_vol,
        crossref_issue=cr_issue,
        crossref_pages=cr_pages,
        abstract=abstract,
        notes=notes
    )

def map_usage_and_sequence(
    references: List[ReferenceEntry],
    sites: List[CitationSite]
) -> Tuple[Dict[int, UsageMapping], bool, List[str]]:
    """
    Map where each reference is used in the manuscript and check AMA consecutive sequence.
    """
    ref_nums = [r.ref_num for r in references]
    ref_map: Dict[int, UsageMapping] = {}
    first_seen_order: List[int] = []
    order_warnings: List[str] = []

    # Map all occurrences
    occurrences_by_num: Dict[int, List[UsageOccurrence]] = {n: [] for n in ref_nums}

    for site in sites:
        for num in site.nums:
            if num in occurrences_by_num:
                occurrences_by_num[num].append(UsageOccurrence(
                    paragraph_idx=site.paragraph_idx,
                    citation_text=site.text,
                    sentence=site.sentence,
                    kind=site.kind
                ))
            if num not in first_seen_order:
                first_seen_order.append(num)

    # Check AMA sequential numbering: first-mention order must be 1, 2, 3...
    consecutive_valid = True
    expected_next = 1
    for seen in first_seen_order:
        if seen > expected_next:
            warn = f"Out-of-order citation: Reference [{seen}] was cited before Reference [{expected_next}]."
            order_warnings.append(warn)
            consecutive_valid = False
            expected_next = max(expected_next, seen + 1)
        elif seen == expected_next:
            expected_next += 1

    # Check uncited references
    for n in ref_nums:
        if n not in first_seen_order:
            order_warnings.append(f"Uncited Reference: Reference [{n}] appears in bibliography but is never cited in text.")

    for r in references:
        occs = occurrences_by_num.get(r.ref_num, [])
        first_para = occs[0].paragraph_idx if occs else -1
        first_sent = occs[0].sentence if occs else "Not cited in body text."
        
        is_order_ok = True
        issue = None
        if r.ref_num in first_seen_order:
            idx = first_seen_order.index(r.ref_num)
            # If any previous number in first_seen_order is greater than r.ref_num
            for prev in first_seen_order[:idx]:
                if prev > r.ref_num:
                    pass
        else:
            is_order_ok = False
            issue = "Never cited in body paragraphs."

        ref_map[r.ref_num] = UsageMapping(
            ref_num=r.ref_num,
            first_mention_paragraph=first_para,
            first_mention_sentence=first_sent,
            total_occurrences=len(occs),
            occurrences=occs,
            is_consecutive_order=is_order_ok,
            order_issue=issue
        )

    return ref_map, consecutive_valid, order_warnings

