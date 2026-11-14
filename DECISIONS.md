# Co-Scientist Reference Auditor & Zotero Linker: Decision & Audit Ledger

## Architecture Invariants
- **Runtime Mode 1**: Pure in-browser client-side execution via GitHub Pages (`JSZip` + XML DOMParser + Crossref CORS API).
- **Runtime Mode 2**: Connected FastAPI server with local Desktop Zotero API (`localhost:23119`) and local LLM context checking (`localhost:18000`).
- **OOXML Field Standard**: Strict adherence to Microsoft Word field structure (`ADDIN ZOTERO_ITEM`, `ADDIN ZOTERO_BIBL`, `ADDIN ZOTERO_PREF_1`).
- **Academic Editorial Theme**: 7-color palette (`#3a0f34` Primary Wine, `#fbf9f4` Paper Canvas, `#814d75` Editorial Plum, `#d2c2cb` Border Outline).
- **Zero Patented Disclosures**: Universally branded as **"Co-Scientist Reference Auditor & Zotero Linker"**.

---

## Log of State Transitions & Architectural Decisions

### [2026-11-14 06:36] ARCH-DECISION-001: Dual-Engine Architecture
- **Context**: User plans to deploy the tool to a live GitHub Pages site where users upload Word `.docx` files directly.
- **Decision**: Implemented dual-engine design:
  1. Client-Side JavaScript Engine (`docx_engine.js` using JSZip) for 100% serverless, zero-cost GitHub Pages static deployment.
  2. Python FastAPI Backend Engine (`server/`) for local CLI, automated test suites, and direct local Zotero desktop API library injection.
- **Guard**: In-browser engine must produce byte-level compatible XML structures with Python `python-docx` linker.


### [2026-11-14 06:44] ARCH-DECISION-002: High-Precision Citation vs. Text Number Discrimination
- **Context**: The engine must never confuse plain numbers (e.g. `stage (1)`, `p < 0.05`, `95% CI`, `15 cm3`, `R2`) with bibliographic citations.
- **Decision**: Added multi-layer discrimination guards across both Python backend and JavaScript client engines:
  1. Upper-bound range gating: Numbers exceeding bibliography size ($N$) are rejected (e.g. years `(2020)` or sample sizes `(150)`).
  2. Classification noun lookbehind: Excludes numbers preceded by `stage`, `case`, `grade`, `type`, `group`, `cohort`, `sample`, `patient`, `Table`, `Figure`.
  3. Enumerated itemized list guards: Excludes `(1) Capitalized text...` beginning a sentence.
  4. Exponent and unit lookbehinds: Excludes superscripts preceded by statistical characters ($R^2$, $\chi^2$, $\tau^2$, $I^2$, $\beta$) or physical units ($cm^3$, $mm^2$, $m^2$, $kg$).
  5. Affiliation lookbehind: Excludes author superscripts preceded by characters like `MD1`, `PhD2`.
- **Verification**: Verified via test `test_06_citation_vs_number_discrimination` in `tests/test_engine.py` (100% pass rate).

### [2026-11-14 06:52] ARCH-DECISION-003: Newspaper Newsprint Editorial Broadside Aesthetic
- **Context**: User requested the full implementation of the vintage newspaper newsprint styling.
- **Decision**: Implemented broadsheet typography:
  - Masthead: `UnifrakturMaguntia` / `Newsreader` with folios (`VOL. CXXVI • NO. 42`), authentic double rules (`3px double #2f2f2f`), and Roman numeral navigation (`I. INGEST MANUSCRIPT`, `II. REACHABILITY AUDIT`, `III. SENTENCE EXPLORER`, `IV. ZOTERO DELIVERABLES`).
  - Palette: Authentic warm newsprint paper (`#f9f7f1`), aged ink (`#2f2f2f`), faint ink (`#8a8a8a`), hairline rules (`#c4c0b6`), and archival crimson accents (`#8b0000`).
  - Typography: `Newsreader` for headlines, `Merriweather` for reading body, and `Source Sans 3` for controls.
  - Colophon footer and archival stamp status badges.
- **Empirical Verification**: End-to-end verified in live browser session on `http://localhost:8765` by UI Verifier subagent.

### [2026-11-14 07:53] ARCH-DECISION-004: Real-World Clinical Manuscript Stress Testing (ACTA2 Review)
- **Context**: User submitted a real-world clinical systematic review manuscript `ACTA2_Manuscript_11.14.2026.docx` (185 KB, 176 paragraphs, 11 tables, 43 references) to stress-test and fix all potential edge cases.
- **Audits & Remediations**:
  1. **Hyphenated Superscript Range Bug**: Detected that superscript range notation (e.g. `11-42`) was splitting into boundary elements `[11, 42]` rather than expanding sequentially `[11..42]`. Resolved in both Python `server/parser.py` and JavaScript `static/js/docx_engine.js`.
  2. **Zero Uncited References**: Confirmed 100% of all 43 bibliography entries are cited in the manuscript body.
  3. **AMA Consecutive First-Mention Order**: Confirmed 100% compliance with zero sequence warnings.
  4. **Scholarly Registry Reachability**: Confirmed 43/43 (100%) DOIs resolve to active publisher landing pages via Crossref and DOI resolvers with zero broken links.
  5. **Concurrent Asynchronous Auditing**: Switched validation from sequential to a 10-worker thread pool, accelerating audit latency from 40s to 2.67s.
  6. **Table & OOXML Structural Integrity**: Confirmed all 11 tables, supplementary methods, and all 176 paragraphs remain identical without corruption.
  7. **Native Zotero Field Injection**: Successfully generated `ACTA2_Manuscript_zotero_linked.docx` with 56 `ADDIN ZOTERO_ITEM` fields, `ADDIN ZOTERO_BIBL`, and `ADDIN ZOTERO_PREF_1`.
- **Verification**: Verified via test `test_08_acta2_real_world_manuscript` in `tests/test_engine.py` (8/8 tests passing).
