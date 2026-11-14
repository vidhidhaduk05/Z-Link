/**
 * Standards-compliant RIS Generator for Browser & Zotero Import
 */

export function generateClientRis(references, verdicts = {}) {
  const lines = [];

  for (const ref of references) {
    const v = verdicts[ref.ref_num] || {};
    const title = v.crossref_title || ref.title || "Untitled Article";
    const authors = (v.crossref_authors && v.crossref_authors.length > 0) ? v.crossref_authors : (ref.authors || ["Unknown Author"]);
    const journal = v.crossref_journal || ref.journal || "";
    const year = v.crossref_year || ref.year || "";
    const volume = v.crossref_volume || ref.volume || "";
    const issue = v.crossref_issue || ref.issue || "";
    const pages = v.crossref_pages || ref.pages || "";
    const doi = ref.doi || "";

    lines.push("TY  - JOUR");
    for (const a of authors) {
      lines.push(`AU  - ${a}`);
    }
    lines.push(`TI  - ${title}`);
    if (journal) {
      lines.push(`JO  - ${journal}`);
      lines.push(`TA  - ${journal}`);
    }
    if (year) lines.push(`PY  - ${year}`);
    if (volume) lines.push(`VL  - ${volume}`);
    if (issue) lines.push(`IS  - ${issue}`);
    if (pages) lines.push(`SP  - ${pages}`);
    if (doi) {
      lines.push(`DO  - ${doi}`);
      lines.push(`UR  - https://doi.org/${doi}`);
    }
    lines.push("ER  - ");
    lines.push("");
  }

  return lines.join("\n");
}
