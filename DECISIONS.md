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
