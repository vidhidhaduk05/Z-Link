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
