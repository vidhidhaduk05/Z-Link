---
id: "skill_7c3f2a91e5d84b60a1f4c8e2d95b0a73"
name: "zotero-linked-references"
description: "Use to audit, correct, superscript, and deliver Zotero-linked references for numbered-citation manuscripts (AMA/Radiology style): verifies every reference against Crossref/PubMed, fixes metadata and context errors, converts in-text citations to AMA superscript, generates a corrected RIS, and hands off a tested local script that injects native Zotero citation and bibliography fields through the user's Zotero local API."
category: "general"
visibility: "public"
starting-prompt: "Can you check the references in my manuscript and give me a Zotero-linked version I can keep editing with the Zotero Word plugin?"
---

# Zotero-Linked References

End-to-end reference workflow for manuscripts that use numbered citations and
Zotero for reference management. The outcome is a manuscript whose citations are
**live Zotero fields** (not static text), so the user can add or remove references
through the Zotero Word plugin and Zotero renumbers everything automatically.

## Scope and boundaries

- Applies to .docx manuscripts with numbered citations, either parenthetical
  `(1, 2)` / `(1-3)` or already superscript, destined for AMA-style journals
  (Radiology, RSNA journals, and any AMA 11th-edition venue).
- The sandbox can verify references against Crossref and PubMed and can edit the
  .docx. It **cannot reach the user's Zotero local API** (`localhost:23119` runs
  on the user's machine). The final linking step therefore runs as a local script
  the user executes; this skill delivers and explains that script.
- Never change prose, tables, figures, or front matter beyond (a) in-text
  citation formatting and (b) verified reference-list corrections. If a
  correction outside the reference list seems necessary, ask first.
- Do not fabricate bibliographic metadata. Anything unverifiable is flagged as
  such, never guessed.

## Workflow

### 1. Extract and map citations

- Extract the full reference list and every in-text citation with its surrounding
  sentence (python-docx; tables and supplement usually contain no citations —
  verify).
- Record the first-appearance order. AMA requires references numbered
  consecutively by first mention; report any deviation.

### 2. Verify every reference (metadata + context)

- Resolve each DOI against the Crossref API; confirm authors (order and
  initials), title, journal abbreviation (NLM style), year, volume, issue,
  pages/elocation, and DOI.
- For entries without DOIs, verify via PubMed E-utilities (esearch + efetch).
- Judge usage context: fetch each source's abstract and check that the cited
  claim matches what the source actually reports. Flag claims no listed source
  supports.
- Report per-reference verdicts: OK / format issue / context concern, with the
  exact correction. Save the full audit as a Markdown report for the user.

### 3. Produce the corrected, superscripted manuscript

- Apply verified corrections to the reference list only.
- Convert parenthetical citations to AMA superscript: numerals outside
  punctuation ("…evaluation.1-3"), no spaces after commas ("7,9,10"), hyphen
  ranges without spaces. Edit runs in place (python-docx) so all other
  formatting survives; never rebuild the document.
- Guard rails: restrict conversion to body paragraphs (stop at the REFERENCES
  header) so volume/issue parentheses in the reference list are not mangled;
  verify with a full-text diff that only citation sites and reference entries
  changed.
- Save as `<manuscript>_v<next>_superscript.docx` in the results folder.

### 4. Generate the corrected RIS

- One RIS entry per reference with full author lists, title, journal (full +
  NLM abbreviation), year, volume, issue, pages/elocation, and DOI.
- This file is the import source for Zotero and the matching key set (DOI) for
  the linker.

### 5. Hand off the local linking step

- Give the user `scripts/zotero_manuscript_linker.py` (copy it next to the
  deliverables) and the two commands:

  ```
  pip install requests python-docx
  python zotero_manuscript_linker.py manuscript.docx references.ris
  ```

- The script runs on the user's machine with the Zotero desktop app open. It
  reads the library through the local API, imports missing references
  (Zotero 10+; older versions get a manual File → Import fallback), matches by
  DOI, fetches CSL-JSON, converts the superscript citations into native
  `ADDIN ZOTERO_ITEM` fields, wraps the reference list in an
  `ADDIN ZOTERO_BIBL` field, writes AMA document preferences, and saves
  `<name>_zotero_linked.docx`.
- `--dry-run` reports the Zotero match rate without writing anything.

### 6. User verification and ongoing editing

- One-time check: open the linked document in Word with Zotero running, click
  **Refresh** (everything re-renders unchanged), then click any superscript
  number → **Add/Edit Citation** opens the Zotero picker.
- If Refresh reports no Zotero fields: Document Preferences → select the AMA
  style → Refresh again.
- Thereafter the user adds/removes references through the Zotero plugin; Zotero
  renumbers automatically. Never retype citation numbers by hand.

## Detection caveats (linker script)

- Citation-site detection excludes author-affiliation superscripts (preceded by
  a digit, e.g. "MD1") and statistical exponents (R2, chi2, tau2, I2, beta
  exponents), and only scans body paragraphs between the abstract/introduction
  and the REFERENCES header.
- The script prints every detected site with context and asks for confirmation
  (`--yes` skips) before writing. Review the list; a misdetected site is a
  reason to stop, not to click through.
- The script was validated end-to-end against a simulated Zotero local API
  (matching, import, CSL fetch, field injection, byte-identical visible text,
  well-formed OOXML). A live-Zotero Refresh on the user's machine is the final
  verification and belongs to the user.

## Stopping conditions

- Any citation-site fingerprint mismatch when linking: abort, do not guess.
- References that cannot be verified externally: deliver flagged, not silently
  "corrected".
- Requests to change prose beyond citations/reference list: ask before acting.
