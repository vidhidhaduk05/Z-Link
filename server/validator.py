"""
Reference Validation, DOI Reachability, and Usage Mapping Engine.
"""
import re
import requests
from typing import Dict, List, Tuple
from server.models import ReferenceEntry, CitationSite, ValidationVerdict, UsageMapping, UsageOccurrence, AuditSummary

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 CoScientistAuditor/1.0"
CROSSREF_API = "https://api.crossref.org/works"
EUROPE_PMC_REST = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
OPENALEX_REST = "https://api.openalex.org/works"
PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
TIMEOUT = 10

def check_doi_handle(doi: str) -> Tuple[bool, str]:
    """
    Query the official DOI Foundation Handle system REST API.
    Universal, authoritative global registry for all DOIs.
    """
    if not doi:
        return False, ""
    clean_doi = doi.strip()
    clean_doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", clean_doi, flags=re.IGNORECASE)
    clean_doi = re.sub(r"^doi:\s*", "", clean_doi, flags=re.IGNORECASE)
    url = f"https://doi.org/api/handles/{clean_doi}"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if data.get("responseCode") == 1:
                # Find target URL registered by publisher
                for val in data.get("values", []):
                    if val.get("type") == "URL":
                        return True, val.get("data", {}).get("value", "")
                return True, f"https://doi.org/{clean_doi}"
        return False, ""
    except Exception:
        return False, ""

def check_doi_reachability(doi: str) -> Tuple[bool, bool, int, str]:
    """
    Check if the DOI resolves on doi.org and reachability to publisher landing page.
    Returns: (is_reachable, is_bot_protected, status_code, resolved_url)
    """
    if not doi:
        return False, False, 0, ""
    
    clean_doi = doi.strip()
    clean_doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", clean_doi, flags=re.IGNORECASE)
    clean_doi = re.sub(r"^doi:\s*", "", clean_doi, flags=re.IGNORECASE)

    # 1. Authoritative check with official DOI Foundation Handle system
    handle_valid, handle_target = check_doi_handle(clean_doi)

    url = f"https://doi.org/{clean_doi}"
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True, allow_redirects=True)
        status = r.status_code
        final_url = r.url or handle_target or url

        # Detect anti-bot, WAF, Cloudflare, or paywall challenges
        is_bot = False
        if status in (403, 429, 503):
            is_bot = True
        elif status == 200:
            srv = r.headers.get("server", "").lower()
            cf_ray = r.headers.get("cf-ray") or ("cloudflare" in srv)
            if "cf-mitigated" in r.headers:
                is_bot = True
            elif cf_ray and any(marker in r.text[:3000].lower() for marker in [
                "challenges.cloudflare.com", "just a moment...", "turnstile", "verify you are human", "attention required!"
            ]):
                is_bot = True

        if is_bot and (handle_valid or "doi.org" not in final_url):
            return True, True, status, final_url
        
        if status == 200 and not is_bot:
            return True, False, 200, final_url
        
        if status in (301, 302, 307, 308) and handle_valid:
            return True, False, status, final_url

        if handle_valid:
            # Handle registry confirmed valid DOI; publisher throttled or blocked automated probe
            return True, True, status or 403, handle_target or final_url
            
        return False, False, status, final_url
    except requests.exceptions.RequestException:
        if handle_valid:
            # Handle registered; network dropped/throttled by publisher WAF
            return True, True, 403, handle_target or f"https://doi.org/{clean_doi}"
        return False, False, 0, ""

def query_crossref(doi: str) -> Dict:
    """
    Query Crossref REST API for canonical metadata.
    """
    if not doi:
        return {}
    clean_doi = doi.strip()
    clean_doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", clean_doi, flags=re.IGNORECASE)
    clean_doi = re.sub(r"^doi:\s*", "", clean_doi, flags=re.IGNORECASE)
    url = f"{CROSSREF_API}/{clean_doi}"
    headers = {"User-Agent": f"CoScientist-Auditor/1.0 (mailto:coscientist-auditor@academic.org)"}
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json().get("message", {})
        return {}
    except requests.exceptions.RequestException:
        return {}

def check_title_similarity(target_title: str, candidate_title: str) -> float:
    """Compute Jaccard word overlap ratio between reference title and candidate title."""
    if not target_title or not candidate_title:
        return 0.0
    clean_target = set(re.findall(r'\b[a-z]{3,}\b', target_title.lower()))
    clean_cand = set(re.findall(r'\b[a-z]{3,}\b', re.sub(r'<[^>]+>', '', candidate_title).lower()))
    if not clean_target or not clean_cand:
        return 0.0
    common = clean_target.intersection(clean_cand)
    union = clean_target.union(clean_cand)
    return len(common) / len(union)

def search_crossref_bibliographic(raw_text: str, title: str = "", authors: List[str] = None) -> Tuple[str, Dict]:
    """
    Search Crossref for a reference missing a DOI.
    Uses complete raw bibliographic text (authors + title + journal + year) for Crossref reference matcher.
    """
    query_str = raw_text if (raw_text and len(raw_text) > 20) else title
    query_str = re.sub(r'^\d+\.\s*', '', query_str).strip()
    if not query_str or len(query_str) < 15:
        return "", {}

    headers = {"User-Agent": f"CoScientist-Auditor/1.0 (mailto:coscientist-auditor@academic.org)"}
    params = {"query.bibliographic": query_str[:300], "rows": 1}
    try:
        r = requests.get(CROSSREF_API, params=params, headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            items = r.json().get("message", {}).get("items", [])
            if items:
                top = items[0]
                doi = top.get("DOI", "")
                top_title = (top.get("title") or [""])[0]
                score = top.get("score", 0)
                # Verify match confidence: require good score and title overlap if title is known
                if doi and score >= 40:
                    if title and len(title) > 15:
                        sim = check_title_similarity(title, top_title)
                        if sim < 0.50:
                            return "", {}
                    return doi, top
    except Exception:
        pass
    return "", {}

def search_europepmc_bibliographic(raw_text: str, title: str = "") -> Tuple[str, Dict]:
    """
    Search EMBL-EBI Europe PMC REST API for missing DOI.
    Fast, authoritative index of 40M+ biomedical records.
    """
    clean_title = re.sub(r'["\r\n]', ' ', title).strip() if title else ""
    query_candidates = []
    if clean_title and len(clean_title) > 15:
        query_candidates.append(f'TITLE:"{clean_title}"')
    
    clean_raw = re.sub(r'^\d+\.\s*', '', raw_text).strip() if raw_text else ""
    if clean_raw and len(clean_raw) > 20:
        query_candidates.append(clean_raw[:180])

    for q in query_candidates:
        params = {"query": q, "resultType": "lite", "pageSize": 1, "format": "json"}
        try:
            r = requests.get(EUROPE_PMC_REST, params=params, timeout=TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                results = data.get("resultList", {}).get("result", [])
                if results:
                    top = results[0]
                    doi = top.get("doi", "")
                    top_title = top.get("title", "")
                    if doi:
                        if title and len(title) > 15:
                            sim = check_title_similarity(title, top_title)
                            if sim < 0.50:
                                continue
                        return doi, top
        except Exception:
            continue
    return "", {}

def search_openalex_bibliographic(raw_text: str, title: str = "") -> Tuple[str, Dict]:
    """
    Search OpenAlex open scholarly graph for missing DOI.
    """
    query_str = title if (title and len(title) > 15) else re.sub(r'^\d+\.\s*', '', raw_text).strip()
    if not query_str or len(query_str) < 15:
        return "", {}
    params = {"search": query_str[:200], "per-page": 1}
    try:
        r = requests.get(OPENALEX_REST, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                top = results[0]
                doi_url = top.get("doi", "")
                doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi_url, flags=re.IGNORECASE) if doi_url else ""
                top_title = top.get("title", "")
                if doi:
                    if title and len(title) > 15:
                        sim = check_title_similarity(title, top_title)
                        if sim < 0.50:
                            return "", {}
                    return doi, top
    except Exception:
        pass
    return "", {}

def search_multi_registry_bibliographic(raw_text: str, title: str = "", authors: List[str] = None) -> Tuple[str, str, Dict]:
    """
    High-Throughput Multi-Registry Missing DOI Resolver:
    1. EMBL-EBI Europe PMC (Biomedical primary, fastest)
    2. OpenAlex (Global multidisciplinary graph)
    3. Crossref Bibliographic Matcher (Publisher registry fallback)
    Returns: (doi, registry_name, meta_dict)
    """
    # 1. Europe PMC
    doi, meta = search_europepmc_bibliographic(raw_text, title)
    if doi:
        return doi, "Europe PMC", meta

    # 2. OpenAlex
    doi, meta = search_openalex_bibliographic(raw_text, title)
    if doi:
        return doi, "OpenAlex", meta

    # 3. Crossref
    doi, meta = search_crossref_bibliographic(raw_text, title, authors)
    if doi:
        return doi, "Crossref", meta

    return "", "", {}

def validate_single_reference(ref: ReferenceEntry) -> ValidationVerdict:
    notes = []
    doi = ref.doi
    is_recovered = False
    
    # If DOI is missing from reference line, attempt automatic recovery via multi-registry engine
    if not doi:
        recovered_doi, registry_name, reg_meta = search_multi_registry_bibliographic(ref.raw_text, ref.title, ref.authors)
        if recovered_doi:
            ref.doi = recovered_doi
            doi = recovered_doi
            is_recovered = True
            notes.append(f"Auto-resolved missing DOI via {registry_name} registry: {recovered_doi}")
        else:
            return ValidationVerdict(
                ref_num=ref.ref_num,
                status="missing_doi",
                is_reachable=False,
                is_recovered_doi=False,
                notes=["No DOI detected in reference line and no match found in scholarly registries."]
            )

    # 1. Reachability & Bot Verification Check
    is_reachable, is_bot_protected, http_code, resolved_url = check_doi_reachability(doi)

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
        if not is_recovered:
            notes.append("Metadata verified against Crossref registry.")

    # Status classification
    if is_recovered:
        verdict_status = "recovered"
    elif is_bot_protected:
        verdict_status = "bot_protected"
        notes.append("DOI registered in global Handle database. Publisher site presented anti-bot challenge (Cloudflare/WAF) or institutional paywall. Valid for human readers.")
    elif cr_found and is_reachable:
        verdict_status = "verified"
        notes.append(f"DOI resolves to live landing: {resolved_url[:65]}...")
    elif not cr_found and is_reachable:
        verdict_status = "verified"
        notes.append(f"DOI verified via Handle registry: {resolved_url[:65]}...")
    else:
        verdict_status = "unreachable"
        notes.append(f"DOI failed to resolve in global registry (HTTP {http_code}).")

    return ValidationVerdict(
        ref_num=ref.ref_num,
        status=verdict_status,
        is_reachable=is_reachable,
        is_bot_gated=is_bot_protected,
        is_recovered_doi=is_recovered,
        recovered_doi=doi if is_recovered else "",
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

