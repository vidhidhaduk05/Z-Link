"""
Domain models and schemas for Co-Scientist Reference Auditor & Zotero Linker.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class CitationSite(BaseModel):
    paragraph_idx: int
    run_idx: int = 0
    kind: str = Field(..., description="'paren' for (1, 2) or 'sup' for superscript")
    text: str
    context_before: str = ""
    sentence: str = ""
    nums: List[int] = Field(default_factory=list)
    match_start: Optional[int] = None
    match_end: Optional[int] = None

class ReferenceEntry(BaseModel):
    ref_num: int
    raw_text: str
    title: str = ""
    authors: List[str] = Field(default_factory=list)
    journal: str = ""
    journal_abbr: str = ""
    year: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    pmid: str = ""

class ValidationVerdict(BaseModel):
    ref_num: int
    status: str = Field("unverified", description="'verified', 'redirected', 'unreachable', 'missing_doi', 'error'")
    is_reachable: bool = False
    http_status: Optional[int] = None
    resolved_url: str = ""
    crossref_found: bool = False
    crossref_title: str = ""
    crossref_authors: List[str] = Field(default_factory=list)
    crossref_journal: str = ""
    crossref_year: str = ""
    crossref_volume: str = ""
    crossref_issue: str = ""
    crossref_pages: str = ""
    abstract: str = ""
    notes: List[str] = Field(default_factory=list)

class UsageOccurrence(BaseModel):
    paragraph_idx: int
    citation_text: str
    sentence: str
    kind: str

class UsageMapping(BaseModel):
    ref_num: int
    first_mention_paragraph: int
    first_mention_sentence: str
    total_occurrences: int
    occurrences: List[UsageOccurrence] = Field(default_factory=list)
    is_consecutive_order: bool = True
    order_issue: Optional[str] = None

class AuditSummary(BaseModel):
    filename: str
    total_citations: int
    total_references: int
    total_reachable: int
    total_broken: int
    total_missing_doi: int
    consecutive_order_valid: bool
    order_warnings: List[str] = Field(default_factory=list)
    sites: List[CitationSite]
    references: List[ReferenceEntry]
    verdicts: Dict[int, ValidationVerdict]
    mappings: Dict[int, UsageMapping]

