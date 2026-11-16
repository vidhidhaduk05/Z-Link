/**
 * In-Browser Docx OOXML Engine & Native Zotero Field Injector
 * Powered by JSZip & browser native XML DOMParser
 */

import {
  CSL_STYLES,
  formatInTextForStyle,
  formatBibliographyForStyle,
  sortReferencesForStyle
} from './csl_formatter.js';

const W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
const DEFAULT_STYLE = "http://www.zotero.org/styles/american-medical-association";
const DEFAULT_STYLE_NAME = "American Medical Association 11th edition";
const CSL_SCHEMA = "https://github.com/citation-style-language/schema/raw/master/csl-citation.json";

const PAREN_REGEX = /\(((?:\d{1,3}(?:\s*[-–—−]\s*\d{1,3})?)(?:\s*,\s*(?:\d{1,3}(?:\s*[-–—−]\s*\d{1,3})?))*)\)/g;
const BRACKET_REGEX = /\[((?:\d{1,3}(?:\s*[-–—−]\s*\d{1,3})?)(?:\s*,\s*(?:\d{1,3}(?:\s*[-–—−]\s*\d{1,3})?))*)]/g;
const SUP_CHAR_REGEX = /^[\d,\s\-–—−]+$/;
const REF_START_REGEX = /^\s*[\(\[]?(\d{1,3})[\)\]\.)]\.?\s*(.*)$/;
const REF_HEADER_REGEX = /^(REFERENCES|Reference List|Bibliography|Works Cited)\s*$/i;
const BODY_START_REGEX = /^(ABSTRACT|SUMMARY STATEMENT|INTRODUCTION|BACKGROUND|Key Results)\s*$/i;
const POST_REF_HEADER_REGEX = /^(Supplementary\s+|Supplemental\s+|Appendix\b|Appendices\b|Tables?\b|Figure\s+Legends?|Figures?\b|Author\s+Contributions|Funding\b|Conflict(?:s)?\s+of\s+Interest|IRB\s+Statement|Informed\s+Consent)/i;
const YEAR_REGEX = /\b(19\d\d|20\d\d)\b/;

const EXPONENT_CHARS = new Set(['R', 'r', 'χ', 'τ', 'I', 'β', 't', 'f', 'z', 'p']);
const EXPONENT_WORDS = ['cm', 'mm', 'nm', 'um', 'µm', 'km', 'm', 'kg', 'mg', 'g', 'ml', 'dl', 'mol', 'chi', 'tau', 'beta', 'st', 'nd', 'rd', 'th'];
const NON_CITATION_PRECEDING_WORDS = /\b(patients?|cases?|cohorts?|subjects?|participants?|controls?|individuals?|males?|females?|men|women|children|adults?|infants?|volunteers?|records?|years?|year-old|aged?|months?|weeks?|days?|hours?|y\/o|yo|n|N|IQR|range|mean|median|SD|SEM|CI|total|subgroups?|proportions?|rates?|counts?|dose|doses|mg|g|ml|mcg|table|fig|figure|equation|eq|formula|model|item|point|rule|part|grade|stage|type|class|step)\s*$/i;
const CLASSIFICATION_NOUNS = NON_CITATION_PRECEDING_WORDS;
const CLINICAL_SCALE_REGEX = /\b(graded\s+(?:on|as|by)?|scores?|scales?|grades?|grading|stages?|staging|classes?|indices?|index|points?|severity|levels?|subscores?|criteria|systems?|angiography|perfusion|tomography|mRS|NIHSS|GCS|mTICI|TICI|TIMI|ASPECTS|DSA)\b/i;
const ENUMERATED_LIST_START = /^\s*\((?:\d{1,2})\)\s+[A-Z]/;

const NON_CITATION_INNER_CONTENT = /(?:%\s*$|\b(?:IQR|range|mean|median|SD|SEM|CI|vs|versus)\b|^[nN]\s*=\s*\d+|\b\d+\s*patients?\b|^\d+\s*,\s*\d+(?:\.\d+)?\s*%|^(?:19\d\d|20\d\d)(?:\s*[-–]\s*(?:19\d\d|20\d\d))?$)/i;

const CLINICAL_STATEMENT_REGEX = /\b(patients?|cases?|cohorts?|subjects?|participants?|controls?|individuals?|were\s+enrolled|underwent|were\s+treated|were\s+evaluated|were\s+included|were\s+admitted|mean\s+age|median\s+age|years?\s+old|inclusion\s+criteria|exclusion\s+criteria|follow-up|in\s+our\s+study|in\s+this\s+study|our\s+cohort|adverse\s+events?|hazard\s+ratio|odds\s+ratio|confidence\s+interval|p\s*[<=]\s*0?\.\d+)\b/i;
const BIBLIO_JOURNAL_PAGINATION_REGEX = /\b(19\d\d|20\d\d)\s*;\s*\d+(?:\s*\([^)]+\))?\s*:\s*[0-9eE\-–]+/;
const BIBLIO_CONTAINERS_REGEX = /\b(et\s+al|doi:|https?:\/\/|PMID:|vol\.|volume|issue|pp\.|pages|press|publisher|springer|elsevier|wiley|oxford|cambridge|academic\s+press|in:\s+[A-Z][a-z]+)\b/i;

// Major Radiology Journals Recognition Dictionary (RSNA, ASNR, ARRS, ESR, SIR, ACR, etc.)
const MAJOR_RADIOLOGY_JOURNAL_MAP = {
  "radiology": ["Radiology", "Radiology"],
  "radiographics": ["RadioGraphics", "RadioGraphics"],
  "american journal of neuroradiology": ["American Journal of Neuroradiology", "AJNR Am J Neuroradiol"],
  "ajnr am j neuroradiol": ["American Journal of Neuroradiology", "AJNR Am J Neuroradiol"],
  "am j neuroradiol": ["American Journal of Neuroradiology", "AJNR Am J Neuroradiol"],
  "ajnr": ["American Journal of Neuroradiology", "AJNR Am J Neuroradiol"],
  "american journal of roentgenology": ["American Journal of Roentgenology", "AJR Am J Roentgenol"],
  "ajr am j roentgenol": ["American Journal of Roentgenology", "AJR Am J Roentgenol"],
  "am j roentgenol": ["American Journal of Roentgenology", "AJR Am J Roentgenol"],
  "ajr": ["American Journal of Roentgenology", "AJR Am J Roentgenol"],
  "european radiology": ["European Radiology", "Eur Radiol"],
  "eur radiol": ["European Radiology", "Eur Radiol"],
  "journal of vascular and interventional radiology": ["Journal of Vascular and Interventional Radiology", "J Vasc Interv Radiol"],
  "j vasc interv radiol": ["Journal of Vascular and Interventional Radiology", "J Vasc Interv Radiol"],
  "jvir": ["Journal of Vascular and Interventional Radiology", "J Vasc Interv Radiol"],
  "journal of the american college of radiology": ["Journal of the American College of Radiology", "J Am Coll Radiol"],
  "j am coll radiol": ["Journal of the American College of Radiology", "J Am Coll Radiol"],
  "jacr": ["Journal of the American College of Radiology", "J Am Coll Radiol"],
  "investigative radiology": ["Investigative Radiology", "Invest Radiol"],
  "invest radiol": ["Investigative Radiology", "Invest Radiol"],
  "academic radiology": ["Academic Radiology", "Acad Radiol"],
  "acad radiol": ["Academic Radiology", "Acad Radiol"],
  "clinical radiology": ["Clinical Radiology", "Clin Radiol"],
  "clin radiol": ["Clinical Radiology", "Clin Radiol"],
  "korean journal of radiology": ["Korean Journal of Radiology", "Korean J Radiol"],
  "korean j radiol": ["Korean Journal of Radiology", "Korean J Radiol"],
  "cardiovascular and interventional radiology": ["CardioVascular and Interventional Radiology", "Cardiovasc Intervent Radiol"],
  "cardiovasc intervent radiol": ["CardioVascular and Interventional Radiology", "Cardiovasc Intervent Radiol"],
  "cvir": ["CardioVascular and Interventional Radiology", "Cardiovasc Intervent Radiol"],
  "neuroradiology": ["Neuroradiology", "Neuroradiology"],
  "pediatric radiology": ["Pediatric Radiology", "Pediatr Radiol"],
  "pediatr radiol": ["Pediatric Radiology", "Pediatr Radiol"],
  "skeletal radiology": ["Skeletal Radiology", "Skeletal Radiol"],
  "skeletal radiol": ["Skeletal Radiology", "Skeletal Radiol"],
  "abdominal radiology": ["Abdominal Radiology", "Abdom Radiol"],
  "abdom radiol": ["Abdominal Radiology", "Abdom Radiol"],
  "the british journal of radiology": ["The British Journal of Radiology", "Br J Radiol"],
  "british journal of radiology": ["The British Journal of Radiology", "Br J Radiol"],
  "br j radiol": ["The British Journal of Radiology", "Br J Radiol"],
  "bjr": ["The British Journal of Radiology", "Br J Radiol"],
  "journal of nuclear medicine": ["Journal of Nuclear Medicine", "J Nucl Med"],
  "j nucl med": ["Journal of Nuclear Medicine", "J Nucl Med"],
  "jnm": ["Journal of Nuclear Medicine", "J Nucl Med"],
  "magnetic resonance in medicine": ["Magnetic Resonance in Medicine", "Magn Reson Med"],
  "magn reson med": ["Magnetic Resonance in Medicine", "Magn Reson Med"],
  "journal of magnetic resonance imaging": ["Journal of Magnetic Resonance Imaging", "J Magn Reson Imaging"],
  "j magn reson imaging": ["Journal of Magnetic Resonance Imaging", "J Magn Reson Imaging"],
  "jmri": ["Journal of Magnetic Resonance Imaging", "J Magn Reson Imaging"],
  "insights into imaging": ["Insights into Imaging", "Insights Imaging"],
  "insights imaging": ["Insights into Imaging", "Insights Imaging"],
  "radiology: artificial intelligence": ["Radiology: Artificial Intelligence", "Radiol Artif Intell"],
  "radiol artif intell": ["Radiology: Artificial Intelligence", "Radiol Artif Intell"],
  "radiology: cardiothoracic imaging": ["Radiology: Cardiothoracic Imaging", "Radiol Cardiothorac Imaging"],
  "radiol cardiothorac imaging": ["Radiology: Cardiothoracic Imaging", "Radiol Cardiothorac Imaging"],
  "radiology: imaging cancer": ["Radiology: Imaging Cancer", "Radiol Imaging Cancer"],
  "radiol imaging cancer": ["Radiology: Imaging Cancer", "Radiol Imaging Cancer"]
};

function isAuthenticBibliographicReference(line) {
  const clean = (line || "").trim();
  if (!clean) return false;
  if (/(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+/i.test(clean) ||
      /\b(10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+)\b/.test(clean) ||
      /PMID:\s*\d{6,9}/i.test(clean)) {
    return true;
  }
  if (BIBLIO_JOURNAL_PAGINATION_REGEX.test(clean)) return true;
  if (CLINICAL_STATEMENT_REGEX.test(clean)) {
    if (!(BIBLIO_CONTAINERS_REGEX.test(clean) && YEAR_REGEX.test(clean))) {
      return false;
    }
  }
  if (BIBLIO_CONTAINERS_REGEX.test(clean) && YEAR_REGEX.test(clean)) return true;
  if (YEAR_REGEX.test(clean) && (clean.includes(';') || clean.includes(':')) && (clean.toLowerCase().includes('et al') || clean.split(/\s+/).length >= 8)) {
    return true;
  }
  return false;
}

function isLikelyReferenceLine(line) {
  return isAuthenticBibliographicReference(line);
}

function extractSurroundingSentence(paraText, matchStart, matchEnd) {
  if (!paraText) return "";
  const sentences = paraText.split(/(?<=[.!?])\s+/);
  let curPos = 0;
  for (const s of sentences) {
    const sStart = curPos;
    const sEnd = curPos + s.length;
    if (sStart <= matchStart && matchStart <= sEnd) {
      return s.trim();
    }
    curPos = sEnd + 1;
  }
  return paraText.slice(0, 140).trim();
}

export function cleanDoi(raw) {
  if (!raw) return "";
  const d = String(raw).trim();
  const m = d.match(/(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)(10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+)/i) ||
            d.match(/\b(10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+)\b/);
  if (m) {
    return m[1].replace(/^[<"'[(]+/, '').replace(/[.,;)\]>'"`]+$/, '');
  }
  return "";
}

function profileDocumentCitationFormat(paragraphs, paraTexts, scanEnd) {
  let supCount = 0;
  let bracketCount = 0;
  let parenCount = 0;

  for (let pi = 0; pi < Math.min(scanEnd, paragraphs.length); pi++) {
    const pEl = paragraphs[pi];
    const runs = Array.from(pEl.getElementsByTagNameNS(W_NS, "r"));
    const spans = [];
    for (let ri = 0; ri < runs.length; ri++) {
      const r = runs[ri];
      const rText = Array.from(r.getElementsByTagNameNS(W_NS, "t")).map(t => t.textContent).join("");
      const rPr = r.getElementsByTagNameNS(W_NS, "rPr")[0];
      const va = rPr ? rPr.getElementsByTagNameNS(W_NS, "vertAlign")[0] : null;
      const isSup = va && va.getAttributeNS(W_NS, "val") === "superscript";
      const canCoalesce = spans.length > 0 && spans[spans.length - 1].isSup === isSup && (!isSup || (SUP_CHAR_REGEX.test(spans[spans.length - 1].text) && SUP_CHAR_REGEX.test(rText)));
      if (canCoalesce) {
        spans[spans.length - 1].text += rText;
      } else {
        spans.push({ text: rText, isSup: isSup });
      }
    }
    let combined = "";
    for (const span of spans) {
      const rText = span.text;
      if (span.isSup && /^\d{1,3}(?:[,-–—−]\d{1,3})*$/.test(rText)) {
        const prevChar = combined.slice(-1);
        const lowerPrev = combined.trim().toLowerCase();
        const isExpWord = EXPONENT_WORDS.some(w => lowerPrev.endsWith(w));
        const isExpChar = EXPONENT_CHARS.has(prevChar) && ['2', '3', '4'].includes(rText);
        if (prevChar && !/\d/.test(prevChar) && !isExpChar && !isExpWord) {
          supCount++;
        }
      }
      combined += rText;
    }
  }

  for (let pi = 0; pi < Math.min(scanEnd, paraTexts.length); pi++) {
    const pText = paraTexts[pi];
    if (!pText.trim()) continue;

    // Brackets
    const bMatches = pText.matchAll(new RegExp(BRACKET_REGEX));
    for (const bm of bMatches) {
      const prior = pText.slice(0, bm.index).trim();
      if (NON_CITATION_PRECEDING_WORDS.test(prior) || CLINICAL_SCALE_REGEX.test(prior.slice(-60))) continue;
      if (NON_CITATION_INNER_CONTENT.test(bm[0].slice(1, -1))) continue;
      const inner = bm[1].replace(/[–—−]/g, '-');
      const parts = inner.split(/\s*,\s*/).filter(Boolean);
      if (parts.length > 0 && parts.every(p => /^\d{1,3}(?:-\d{1,3})?$/.test(p))) {
        if (parts.some(pt => parseInt(pt.split('-')[0], 10) >= 1900)) continue;
        bracketCount++;
      }
    }

    // Parens (applying clinical scale guards)
    const pMatches = pText.matchAll(new RegExp(PAREN_REGEX));
    for (const pm of pMatches) {
      const prior = pText.slice(0, pm.index).trim();
      if (NON_CITATION_PRECEDING_WORDS.test(prior) || CLINICAL_SCALE_REGEX.test(prior.slice(-60))) continue;
      if (NON_CITATION_INNER_CONTENT.test(pm[0].slice(1, -1))) continue;
      const inner = pm[1].replace(/[–—−]/g, '-');
      const parts = inner.split(/\s*,\s*/).filter(Boolean);
      if (parts.length > 0 && parts.every(p => /^\d{1,3}(?:-\d{1,3})?$/.test(p))) {
        if (parts.some(pt => parseInt(pt.split('-')[0], 10) >= 1900)) continue;
        parenCount++;
      }
    }
  }

  // Dominant format determination
  if ((supCount > 0 && bracketCount > 0) || (supCount > 0 && parenCount > 0) || (bracketCount > 0 && parenCount > 0)) {
    return "mixed";
  }
  if (supCount > 0) return "sup";
  if (bracketCount > 0) return "bracket";
  if (parenCount > 0) return "paren";
  return "sup";
}

export function hasTrackedRevisions(xmlDoc) {
  const dels = xmlDoc.getElementsByTagNameNS(W_NS, "del");
  const inss = xmlDoc.getElementsByTagNameNS(W_NS, "ins");
  return (dels.length > 0 || inss.length > 0);
}

export function acceptPriorRevisions(xmlDoc) {
  const dels = Array.from(xmlDoc.getElementsByTagNameNS(W_NS, "del"));
  dels.forEach(delEl => {
    if (delEl.parentNode) {
      delEl.parentNode.removeChild(delEl);
    }
  });

  const inss = Array.from(xmlDoc.getElementsByTagNameNS(W_NS, "ins"));
  inss.forEach(insEl => {
    const parent = insEl.parentNode;
    if (parent) {
      while (insEl.firstChild) {
        parent.insertBefore(insEl.firstChild, insEl);
      }
      parent.removeChild(insEl);
    }
  });
}

export async function parseDocxFile(fileOrBuffer, citationFormat = "auto") {
  if (!window.JSZip) {
    throw new Error("JSZip library not loaded.");
  }

  let data = fileOrBuffer;
  if (fileOrBuffer && typeof fileOrBuffer.arrayBuffer === "function") {
    data = await fileOrBuffer.arrayBuffer();
  }

  const zip = await window.JSZip.loadAsync(data);
  const docXmlStr = await zip.file("word/document.xml").async("text");
  
  const parser = new DOMParser();
  const xmlDoc = parser.parseFromString(docXmlStr, "application/xml");
  // Non-destructive: preserve existing reviewer revisions without accepting them
  const paragraphs = Array.from(xmlDoc.getElementsByTagNameNS(W_NS, "p"));

  const paraTexts = paragraphs.map(p => {
    const runs = Array.from(p.getElementsByTagNameNS(W_NS, "r")).filter(r => !r.closest("w\\:del, del"));
    return runs.map(r => {
      let rText = "";
      for (let ci = 0; ci < r.childNodes.length; ci++) {
        const child = r.childNodes[ci];
        if (child.localName === "t") {
          rText += child.textContent || "";
        } else if (child.localName === "br") {
          rText += "\n";
        }
      }
      return rText;
    }).join("");
  });

  // 1. Identify reference section
  let refHdrIdx = -1;
  for (let i = 0; i < paraTexts.length; i++) {
    if (REF_HEADER_REGEX.test(paraTexts[i].trim())) {
      refHdrIdx = i;
      break;
    }
  }

  const scanEnd = (refHdrIdx !== -1) ? refHdrIdx : paraTexts.length;

  // 2. Parse references
  const references = [];
  const startRef = (refHdrIdx !== -1) ? refHdrIdx : 0;
  for (let i = startRef; i < paraTexts.length; i++) {
    const rawPara = paraTexts[i].trim();
    if (!rawPara) continue;
    // Stop if a post-reference section begins (e.g. Supplementary, Figures, Tables)
    if (refHdrIdx !== -1 && i > refHdrIdx && POST_REF_HEADER_REGEX.test(rawPara) && references.length > 0) {
      break;
    }
    const subLines = rawPara.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    for (const line of subLines) {
      const m = line.match(REF_START_REGEX);
      if (m) {
        const refNum = parseInt(m[1], 10);
        const content = m[2];
        if (isLikelyReferenceLine(content) || (i + 1 < paraTexts.length && (REF_START_REGEX.test(paraTexts[i+1].trim()) && isLikelyReferenceLine(paraTexts[i+1].trim())))) {
          const doi = cleanDoi(content);

          const parts = content.split(". ");
          const authors = parts.length > 0 ? parts[0].split(/,| and /).map(a => a.trim()).filter(Boolean) : [];
          const title = parts.length > 1 ? parts[1].trim() : "";

          let journal = "";
          let journalAbbr = "";
          const lowerLine = line.toLowerCase();
          for (const [pattern, [jFull, jAbbr]] of Object.entries(MAJOR_RADIOLOGY_JOURNAL_MAP)) {
            const reg = new RegExp(`\\b${pattern}\\b`, 'i');
            if (reg.test(lowerLine)) {
              journal = jFull;
              journalAbbr = jAbbr;
              break;
            }
          }
          if (!journal && parts.length >= 3) {
            const cand = parts[2].split(/\b(19\d\d|20\d\d)\b|;/)[0].trim().replace(/\.+$/, '');
            if (cand && cand.length > 1 && !/^\d+$/.test(cand)) {
              journal = cand;
            }
          }

          references.push({
            ref_num: refNum,
            raw_text: line,
            title: title,
            authors: authors,
            journal: journal,
            journal_abbr: journalAbbr,
            year: "",
            volume: "",
            issue: "",
            pages: "",
            doi: doi
          });
        }
      } else if (references.length > 0) {
        // Check multi-line reference continuation (e.g. wrapped DOI or PMID on subsequent line/paragraph)
        const contDoi = cleanDoi(line);
        if (contDoi) {
          const lastRef = references[references.length - 1];
          lastRef.raw_text += " " + line;
          if (!lastRef.doi) {
            lastRef.doi = contDoi;
          }
        }
      }
    }
  }

  // Determine effective format via Pass 1 profiling if auto
  let effectiveFormat = citationFormat;
  if (citationFormat === "auto") {
    effectiveFormat = profileDocumentCitationFormat(paragraphs, paraTexts, scanEnd);
  }

  // 3. Find body start
  let bodyStart = 0;
  for (let i = 0; i < scanEnd; i++) {
    const t = paraTexts[i].trim();
    if (BODY_START_REGEX.test(t) || t.includes("Corresponding author")) {
      bodyStart = i;
      break;
    }
  }

  // 4. Extract citations
  const sites = [];
  const maxRefNum = references.length > 0 ? Math.max(...references.map(r => r.ref_num)) : 999;

  for (let pi = bodyStart; pi < scanEnd; pi++) {
    const pEl = paragraphs[pi];
    const pText = paraTexts[pi];
    if (!pText.trim()) continue;

    const runs = Array.from(pEl.getElementsByTagNameNS(W_NS, "r")).filter(r => !r.closest("w\\:del, del"));

    // Coalesce adjacent runs sharing identical vertAlign="superscript"
    const spans = [];
    for (let ri = 0; ri < runs.length; ri++) {
      const r = runs[ri];
      const rText = Array.from(r.getElementsByTagNameNS(W_NS, "t")).map(t => t.textContent).join("");
      const rPr = r.getElementsByTagNameNS(W_NS, "rPr")[0];
      const va = rPr ? rPr.getElementsByTagNameNS(W_NS, "vertAlign")[0] : null;
      const isSup = va && va.getAttributeNS(W_NS, "val") === "superscript";
      const canCoalesce = spans.length > 0 && spans[spans.length - 1].isSup === isSup && (!isSup || (SUP_CHAR_REGEX.test(spans[spans.length - 1].text) && SUP_CHAR_REGEX.test(rText)));

      if (canCoalesce) {
        spans[spans.length - 1].text += rText;
        spans[spans.length - 1].endRunIdx = ri;
        spans[spans.length - 1].runs.push(r);
      } else {
        spans.push({
          text: rText,
          isSup: isSup,
          startRunIdx: ri,
          endRunIdx: ri,
          runs: [r]
        });
      }
    }

    // 1. Superscript check over coalesced spans
    let combinedPrev = "";
    for (const span of spans) {
      const rText = span.text;
      const ri = span.startRunIdx;
      const endRi = span.endRunIdx;
      if ((effectiveFormat === "auto" || effectiveFormat === "sup" || effectiveFormat === "mixed") && span.isSup && /^\d{1,3}(?:[,-–—−]\d{1,3})*$/.test(rText)) {
        const inner = rText.replace(/[–—−]/g, '-');
        const nums = [];
        inner.split(/\s*,\s*/).forEach(part => {
          if (part.includes('-')) {
            const sp = part.split('-');
            const s0 = parseInt(sp[0], 10);
            const s1 = parseInt(sp[1], 10);
            if (!isNaN(s0) && !isNaN(s1)) {
              for (let k = s0; k <= s1; k++) nums.push(k);
            }
          } else {
            const n = parseInt(part, 10);
            if (!isNaN(n)) nums.push(n);
          }
        });

        const prevChar = combinedPrev.slice(-1);
        const lowerPrev = combinedPrev.trim().toLowerCase();
        
        // Exclude affiliations, exponents, and physical units
        const isExpWord = EXPONENT_WORDS.some(w => lowerPrev.endsWith(w));
        const isExpChar = EXPONENT_CHARS.has(prevChar) && ['2', '3', '4'].includes(rText);

        if (prevChar && !/\d/.test(prevChar) && !isExpChar && !isExpWord) {
          if (nums.every(n => n < 1900) && Math.max(...nums) <= maxRefNum) {
            const mStart = combinedPrev.length;
            const mEnd = mStart + rText.length;
            const sent = extractSurroundingSentence(pText, mStart, mEnd);
            sites.push({
              paragraph_idx: pi,
              run_idx: ri,
              end_run_idx: endRi,
              kind: "sup",
              text: rText,
              context_before: combinedPrev.slice(-40),
              sentence: sent,
              nums: Array.from(new Set(nums)).sort((a,b) => a - b),
              match_start: mStart,
              match_end: mEnd
            });
          }
        }
      }
      combinedPrev += rText;
    }

    // Helper to map paragraph character offsets to run index span
    function findRunSpan(mStart, mEnd) {
      let runI = 0;
      let endRunI = 0;
      let curPos = 0;
      for (let rIdx = 0; rIdx < runs.length; rIdx++) {
        const rLen = Array.from(runs[rIdx].getElementsByTagNameNS(W_NS, "t")).map(t => t.textContent).join("").length;
        if (curPos <= mStart && mStart < curPos + rLen) {
          runI = rIdx;
        }
        if (curPos < mEnd && mEnd <= curPos + rLen) {
          endRunI = rIdx;
          break;
        }
        curPos += rLen;
      }
      return { runI, endRunI };
    }

    // 2. Square Bracket match [1, 2] across paragraph text
    if (effectiveFormat === "auto" || effectiveFormat === "bracket" || effectiveFormat === "mixed") {
      const bMatches = pText.matchAll(new RegExp(BRACKET_REGEX));
      for (const bm of bMatches) {
        const contextPrior = pText.slice(0, bm.index).trim();
        if (NON_CITATION_PRECEDING_WORDS.test(contextPrior) || CLINICAL_SCALE_REGEX.test(contextPrior.slice(-60))) {
          continue;
        }
        if (NON_CITATION_INNER_CONTENT.test(bm[0].slice(1, -1))) {
          continue;
        }

        const inner = bm[1].replace(/[–—−]/g, '-');
        const nums = [];
        inner.split(/\s*,\s*/).forEach(part => {
          if (part.includes('-')) {
            const sp = part.split('-');
            const s0 = parseInt(sp[0], 10);
            const s1 = parseInt(sp[1], 10);
            if (!isNaN(s0) && !isNaN(s1)) {
              for (let k = s0; k <= s1; k++) nums.push(k);
            }
          } else {
            const n = parseInt(part, 10);
            if (!isNaN(n)) nums.push(n);
          }
        });

        if (nums.length > 0 && nums.every(n => n < 1900) && Math.max(...nums) <= maxRefNum) {
          const globalStart = bm.index;
          const globalEnd = globalStart + bm[0].length;
          const sent = extractSurroundingSentence(pText, globalStart, globalEnd);
          const { runI, endRunI } = findRunSpan(globalStart, globalEnd);
          sites.push({
            paragraph_idx: pi,
            run_idx: runI,
            end_run_idx: endRunI,
            kind: "bracket",
            text: bm[0],
            context_before: pText.slice(Math.max(0, globalStart - 40), globalStart),
            sentence: sent,
            nums: Array.from(new Set(nums)).sort((a,b) => a - b),
            match_start: globalStart,
            match_end: globalEnd
          });
        }
      }
    }

    // 3. Parenthetical match (1, 2) across paragraph text
    if (effectiveFormat === "auto" || effectiveFormat === "paren" || effectiveFormat === "mixed") {
      const pMatches = pText.matchAll(new RegExp(PAREN_REGEX));
      for (const pm of pMatches) {
        const contextPrior = pText.slice(0, pm.index).trim();
        if (NON_CITATION_PRECEDING_WORDS.test(contextPrior) || CLINICAL_SCALE_REGEX.test(contextPrior.slice(-60))) {
          continue;
        }
        if (NON_CITATION_INNER_CONTENT.test(pm[0].slice(1, -1))) {
          continue;
        }
        const trailing = pText.slice(pm.index, pm.index + pm[0].length + 20);
        if (ENUMERATED_LIST_START.test(trailing) && !contextPrior) {
          continue;
        }

        const inner = pm[1].replace(/[–—−]/g, '-');
        const nums = [];
        let hasZero = false;
        inner.split(/\s*,\s*/).forEach(part => {
          if (part.includes('-')) {
            const sp = part.split('-');
            const s0 = parseInt(sp[0], 10);
            const s1 = parseInt(sp[1], 10);
            if (!isNaN(s0) && !isNaN(s1)) {
              if (s0 <= 0 || s1 <= 0) {
                hasZero = true;
                return;
              }
              for (let k = s0; k <= s1; k++) nums.push(k);
            }
          } else {
            const n = parseInt(part, 10);
            if (!isNaN(n)) {
              if (n <= 0) {
                hasZero = true;
                return;
              }
              nums.push(n);
            }
          }
        });

        if (hasZero || nums.length === 0) {
          continue;
        }

        if (nums.every(n => n < 1900) && Math.max(...nums) <= maxRefNum) {
          const globalStart = pm.index;
          const globalEnd = globalStart + pm[0].length;
          const sent = extractSurroundingSentence(pText, globalStart, globalEnd);
          const { runI, endRunI } = findRunSpan(globalStart, globalEnd);
          sites.push({
            paragraph_idx: pi,
            run_idx: runI,
            end_run_idx: endRunI,
            kind: "paren",
            text: pm[0],
            context_before: pText.slice(Math.max(0, globalStart - 40), globalStart),
            sentence: sent,
            nums: Array.from(new Set(nums)).sort((a,b) => a - b),
            match_start: globalStart,
            match_end: globalEnd
          });
        }
      }
    }
  }

  return {
    zip,
    xmlDoc,
    paraTexts,
    paragraphs,
    sites,
    references,
    refHdrIdx,
    detectedFormat: effectiveFormat
  };
}

function createFieldRun(doc, type, instrText = null) {
  const r = doc.createElementNS(W_NS, "w:r");
  const rPr = doc.createElementNS(W_NS, "w:rPr");
  const vanish = doc.createElementNS(W_NS, "w:vanish");
  rPr.appendChild(vanish);
  r.appendChild(rPr);

  if (["begin", "separate", "end"].includes(type)) {
    const fldChar = doc.createElementNS(W_NS, "w:fldChar");
    fldChar.setAttributeNS(W_NS, "w:fldCharType", type);
    r.appendChild(fldChar);
  } else {
    const it = doc.createElementNS(W_NS, "w:instrText");
    it.setAttribute("xml:space", "preserve");
    it.textContent = ` ${instrText} `;
    r.appendChild(it);
  }
  return r;
}

function stripExistingBibliographyFields(xmlDoc) {
  const instrs = xmlDoc.getElementsByTagNameNS(W_NS, "instrText");
  const runsToRemove = [];

  for (let i = 0; i < instrs.length; i++) {
    const it = instrs[i];
    if (it.textContent && it.textContent.includes("ZOTERO_BIBL")) {
      let r = it.parentElement;
      while (r && r.localName !== "r" && r !== xmlDoc.documentElement) {
        r = r.parentElement;
      }
      if (r && r.localName === "r") {
        runsToRemove.push(r);
        let prev = r.previousElementSibling;
        while (prev) {
          if (prev.localName === "r") {
            const fcs = prev.getElementsByTagNameNS(W_NS, "fldChar");
            if (fcs.length > 0 && fcs[0].getAttributeNS(W_NS, "fldCharType") === "begin") {
              runsToRemove.push(prev);
              break;
            }
          }
          prev = prev.previousElementSibling;
        }
        let nxt = r.nextElementSibling;
        while (nxt) {
          if (nxt.localName === "r") {
            const fcs = nxt.getElementsByTagNameNS(W_NS, "fldChar");
            if (fcs.length > 0) {
              const ft = fcs[0].getAttributeNS(W_NS, "fldCharType");
              if (ft === "separate") {
                runsToRemove.push(nxt);
                let subNxt = nxt.nextElementSibling;
                while (subNxt) {
                  if (subNxt.localName === "r") {
                    const sfcs = subNxt.getElementsByTagNameNS(W_NS, "fldChar");
                    if (sfcs.length > 0 && sfcs[0].getAttributeNS(W_NS, "fldCharType") === "end") {
                      runsToRemove.push(subNxt);
                      break;
                    }
                  }
                  subNxt = subNxt.nextElementSibling;
                }
                break;
              } else if (ft === "end") {
                runsToRemove.push(nxt);
                break;
              }
            }
          }
          nxt = nxt.nextElementSibling;
        }
      }
    }
  }

  runsToRemove.forEach(r => {
    if (r.parentNode) r.parentNode.removeChild(r);
  });

  const allP = xmlDoc.getElementsByTagNameNS(W_NS, "p");
  for (let i = 0; i < allP.length; i++) {
    const p = allP[i];
    if (!p.textContent.trim()) {
      const fcs = p.getElementsByTagNameNS(W_NS, "fldChar");
      for (let j = 0; j < fcs.length; j++) {
        if (fcs[j].getAttributeNS(W_NS, "fldCharType") === "end") {
          let pr = fcs[j].parentElement;
          while (pr && pr.localName !== "r" && pr !== p) {
            pr = pr.parentElement;
          }
          if (pr && pr.parentNode) {
            pr.parentNode.removeChild(pr);
          }
        }
      }
    }
  }
}

function createDelRun(doc, text, revId, author = "Vidhi Dhaduk", dateStr = null, isSuperscript = false) {
  const delEl = doc.createElementNS(W_NS, "w:del");
  delEl.setAttributeNS(W_NS, "w:id", String(revId));
  delEl.setAttributeNS(W_NS, "w:author", author);
  delEl.setAttributeNS(W_NS, "w:date", dateStr || new Date().toISOString());

  const r = doc.createElementNS(W_NS, "w:r");
  if (isSuperscript) {
    const rPr = doc.createElementNS(W_NS, "w:rPr");
    const va = doc.createElementNS(W_NS, "w:vertAlign");
    va.setAttributeNS(W_NS, "w:val", "superscript");
    rPr.appendChild(va);
    r.appendChild(rPr);
  }
  const delText = doc.createElementNS(W_NS, "w:delText");
  delText.setAttribute("xml:space", "preserve");
  delText.textContent = text;
  r.appendChild(delText);
  delEl.appendChild(r);
  return delEl;
}

function createInsRun(doc, text, revId, author = "Vidhi Dhaduk", dateStr = null, isSuperscript = false) {
  const insEl = doc.createElementNS(W_NS, "w:ins");
  insEl.setAttributeNS(W_NS, "w:id", String(revId));
  insEl.setAttributeNS(W_NS, "w:author", author);
  insEl.setAttributeNS(W_NS, "w:date", dateStr || new Date().toISOString());

  const r = doc.createElementNS(W_NS, "w:r");
  if (isSuperscript) {
    const rPr = doc.createElementNS(W_NS, "w:rPr");
    const va = doc.createElementNS(W_NS, "w:vertAlign");
    va.setAttributeNS(W_NS, "w:val", "superscript");
    rPr.appendChild(va);
    r.appendChild(rPr);
  }
  const t = doc.createElementNS(W_NS, "w:t");
  t.setAttribute("xml:space", "preserve");
  t.textContent = text;
  r.appendChild(t);
  insEl.appendChild(r);
  return insEl;
}

export function formatCondensedCitation(nums) {
  if (!nums || nums.length === 0) return "";
  const sortedUnique = Array.from(new Set(nums)).sort((a,b) => a - b);
  const ranges = [];
  let start = sortedUnique[0];
  let end = start;

  for (let i = 1; i < sortedUnique.length; i++) {
    const n = sortedUnique[i];
    if (n === end + 1) {
      end = n;
    } else {
      if (end - start >= 2) {
        ranges.push(`${start}-${end}`);
      } else if (end - start === 1) {
        ranges.push(`${start},${end}`);
      } else {
        ranges.push(`${start}`);
      }
      start = n;
      end = n;
    }
  }

  if (end - start >= 2) {
    ranges.push(`${start}-${end}`);
  } else if (end - start === 1) {
    ranges.push(`${start},${end}`);
  } else {
    ranges.push(`${start}`);
  }

  return ranges.join(",");
}

export function buildAmaRenumberingMap(references, sites) {
  const refNums = references.map(r => r.ref_num);
  const firstSeenOrder = [];
  const seenSet = new Set();

  sites.forEach(site => {
    site.nums.forEach(num => {
      if (!seenSet.has(num) && refNums.includes(num)) {
        seenSet.add(num);
        firstSeenOrder.push(num);
      }
    });
  });

  sites.forEach(site => {
    site.nums.forEach(num => {
      if (!seenSet.has(num)) {
        seenSet.add(num);
        firstSeenOrder.push(num);
      }
    });
  });

  const uncited = refNums.filter(n => !seenSet.has(n));
  const mapping = {};

  firstSeenOrder.forEach((oldNum, idx) => {
    mapping[oldNum] = idx + 1;
  });

  const startUncited = firstSeenOrder.length + 1;
  uncited.forEach((oldNum, idx) => {
    mapping[oldNum] = startUncited + idx;
  });

  return { mapping, firstSeenOrder, uncited };
}

export async function injectZoteroFieldsInBrowser(
  parsedData,
  verdicts = {},
  renumberAma = true,
  trackChanges = false,
  author = "Vidhi Dhaduk",
  arg6 = "ama",
  arg7 = undefined
) {
  const targetStyle = (typeof arg7 === "string") ? arg7 : (typeof arg6 === "string" ? arg6 : "ama");
  const { zip, xmlDoc, paragraphs, sites, references } = parsedData;
  let revCounter = 1;
  const dateStr = new Date().toISOString();

  const styleInfo = CSL_STYLES[targetStyle] || CSL_STYLES["ama"];
  const styleId = styleInfo.id;
  const styleName = styleInfo.name;

  // Determine sequential re-numbering map
  let mapping = {};
  if (renumberAma || styleInfo.category === "numeric") {
    const res = buildAmaRenumberingMap(references, sites);
    mapping = res.mapping;
  } else {
    references.forEach(r => { mapping[r.ref_num] = r.ref_num; });
  }

  const cslMap = {};
  for (const ref of references) {
    const v = verdicts[ref.ref_num] || {};
    const newNum = mapping[ref.ref_num] || ref.ref_num;
    const title = v.crossref_title || ref.title || "Article";
    const journal = v.crossref_journal || ref.journal || "";
    const year = v.crossref_year || ref.year || "2020";
    const authors = (v.crossref_authors && v.crossref_authors.length > 0) ? v.crossref_authors : (ref.authors || ["Author"]);
    
    cslMap[newNum] = {
      id: `ITEM-${newNum}`,
      type: "article-journal",
      title: title,
      "container-title": journal,
      volume: v.crossref_volume || ref.volume || "",
      issue: v.crossref_issue || ref.issue || "",
      page: v.crossref_pages || ref.pages || "",
      DOI: ref.doi || "",
      issued: { "date-parts": [[parseInt(year, 10) || 2020]] },
      author: authors.map(a => {
        const sp = a.split(" ");
        return { family: sp[0], given: sp.slice(1).join(" ") };
      })
    };
  }

  // Inject citation fields in reverse
  for (let i = sites.length - 1; i >= 0; i--) {
    const site = sites[i];
    const p = paragraphs[site.paragraph_idx];
    if (!p) continue;

    const runs = Array.from(p.getElementsByTagNameNS(W_NS, "r"));
    if (site.run_idx >= runs.length) continue;
    const targetRun = runs[site.run_idx];

    // Format new numbers / author-date with target style
    const newSiteNums = Array.from(new Set(site.nums.map(n => mapping[n] || n))).sort((a,b) => a - b);
    const citedRefs = site.nums.map(n => references.find(r => r.ref_num === n)).filter(Boolean);
    const inText = formatInTextForStyle(targetStyle, newSiteNums, citedRefs);
    const targetCitStr = inText.text || site.text;
    const isSup = inText.isSuperscript;

    let rPr = targetRun.getElementsByTagNameNS(W_NS, "rPr")[0];
    if (!rPr) {
      rPr = xmlDoc.createElementNS(W_NS, "w:rPr");
      targetRun.insertBefore(rPr, targetRun.firstChild);
    }
    let va = rPr.getElementsByTagNameNS(W_NS, "vertAlign")[0];
    if (isSup) {
      if (!va) {
        va = xmlDoc.createElementNS(W_NS, "w:vertAlign");
        va.setAttributeNS(W_NS, "w:val", "superscript");
        rPr.appendChild(va);
      } else {
        va.setAttributeNS(W_NS, "w:val", "superscript");
      }
    } else if (va) {
      va.setAttributeNS(W_NS, "w:val", "baseline");
    }

    const tNodes = targetRun.getElementsByTagNameNS(W_NS, "t");
    const oldText = (tNodes.length > 0) ? tNodes[0].textContent : site.text;

    let targetAnchor = targetRun;

    if (trackChanges && oldText !== targetCitStr) {
      const delEl = createDelRun(xmlDoc, oldText, revCounter++, author, dateStr, site.kind === "sup");
      const insEl = createInsRun(xmlDoc, targetCitStr, revCounter++, author, dateStr, isSup);
      const runParent = targetRun.parentNode || p;
      runParent.insertBefore(delEl, targetRun);
      runParent.insertBefore(insEl, targetRun);
      runParent.removeChild(targetRun);
      targetAnchor = insEl;
    } else {
      if (tNodes.length > 0) {
        tNodes[0].textContent = targetCitStr;
      }
    }

    // If this site coalesced across multiple runs, empty trailing runs so they don't leave residue
    if (site.end_run_idx && site.end_run_idx > site.run_idx) {
      for (let extraIdx = site.run_idx + 1; extraIdx <= site.end_run_idx && extraIdx < runs.length; extraIdx++) {
        const extraT = runs[extraIdx].getElementsByTagNameNS(W_NS, "t");
        for (let ti = 0; ti < extraT.length; ti++) {
          extraT[ti].textContent = "";
        }
      }
    }

    const citationItems = newSiteNums.map(n => ({
      id: `zotero_key_${n}`,
      uris: [`http://zotero.org/users/0/items/zotero_key_${n}`],
      itemData: cslMap[n] || {}
    }));

    const citationJson = {
      citationID: Math.random().toString(36).substring(2, 10),
      properties: {
        formattedCitation: targetCitStr,
        plainCitation: targetCitStr,
        noteIndex: 0
      },
      citationItems: citationItems,
      schema: CSL_SCHEMA
    };

    const instr = "ADDIN ZOTERO_ITEM CSL_CITATION " + JSON.stringify(citationJson);
    const rBegin = createFieldRun(xmlDoc, "begin");
    const rInstr = createFieldRun(xmlDoc, "instr", instr);
    const rSep = createFieldRun(xmlDoc, "separate");
    const rEnd = createFieldRun(xmlDoc, "end");

    const targetParent = targetAnchor.parentNode || p;
    targetParent.insertBefore(rBegin, targetAnchor);
    targetParent.insertBefore(rInstr, targetAnchor);
    targetParent.insertBefore(rSep, targetAnchor);
    if (targetAnchor.nextSibling) {
      targetParent.insertBefore(rEnd, targetAnchor.nextSibling);
    } else {
      targetParent.appendChild(rEnd);
    }
  }

  // Boundary Isolation & Atomic Reference Blocks
  const REF_HEADER_RE = /^\s*(?:REFERENCES|Reference List|Bibliography|Works Cited)\s*$/i;
  const POST_REF_HEADER_RE = /^\s*(?:Supplementary\s+|Supplemental\s+|Appendix\b|Appendices\b|Tables?\b|Figure\s+Legends?|Figures?\b|Author\s+Contributions|Funding\b|Conflict(?:s)?\s+of\s+Interest|IRB\s+Statement|Informed\s+Consent)/i;
  const REF_START_RE = /^\s*[\(\[]?(\d{1,3})[\)\]\.)]\.?\s*(.*)$/s;

  const getParaText = (p) => {
    const runs = Array.from(p.getElementsByTagNameNS(W_NS, "r")).filter(r => !r.closest("w\\:del, del"));
    return runs.map(r => {
      let rText = "";
      for (let ci = 0; ci < r.childNodes.length; ci++) {
        const child = r.childNodes[ci];
        if (child.localName === "t") {
          rText += child.textContent || "";
        } else if (child.localName === "br") {
          rText += "\n";
        }
      }
      return rText;
    }).join("");
  };

  let headerIdx = -1;
  let startIdx = -1;
  let endIdx = -1;

  for (let i = 0; i < paragraphs.length; i++) {
    const t = getParaText(paragraphs[i]).trim();
    if (REF_HEADER_RE.test(t)) {
      headerIdx = i;
      startIdx = i + 1;
      break;
    }
  }

  if (startIdx === -1) {
    for (let i = 0; i < paragraphs.length; i++) {
      const t = getParaText(paragraphs[i]).trim();
      const m = t.match(REF_START_RE);
      if (m && parseInt(m[1], 10) === 1) {
        startIdx = i;
        break;
      }
    }
  }

  if (startIdx === -1) {
    startIdx = 0;
    endIdx = paragraphs.length;
  } else {
    for (let i = startIdx; i < paragraphs.length; i++) {
      const t = getParaText(paragraphs[i]).trim();
      if (POST_REF_HEADER_RE.test(t)) {
        endIdx = i;
        break;
      }
    }
    if (endIdx === -1) endIdx = paragraphs.length;
  }

  // Split any multi-reference paragraphs separated by newlines/breaks into distinct paragraphs
  let currentEnd = endIdx;
  let pi = startIdx;
  while (pi < currentEnd && pi < paragraphs.length) {
    const p = paragraphs[pi];
    const fullText = getParaText(p).trim();
    const lines = fullText.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    const validMatches = lines.filter(l => REF_START_RE.test(l));
    if (lines.length > 1 && validMatches.length >= 2) {
      const parent = p.parentNode;
      const refChild = p.nextSibling;
      const newPs = [];
      lines.forEach(line => {
        const newP = xmlDoc.createElementNS(W_NS, "w:p");
        const newR = xmlDoc.createElementNS(W_NS, "w:r");
        const newT = xmlDoc.createElementNS(W_NS, "w:t");
        newT.textContent = line;
        newR.appendChild(newT);
        newP.appendChild(newR);
        parent.insertBefore(newP, refChild);
        newPs.push(newP);
      });
      parent.removeChild(p);
      paragraphs.splice(pi, 1, ...newPs);
      currentEnd += (lines.length - 1);
      pi += lines.length;
    } else {
      pi++;
    }
  }
  endIdx = currentEnd;

  // Extract atomic reference blocks within [startIdx, endIdx)
  const blocks = [];
  let currentBlock = null;

  for (let i = startIdx; i < endIdx; i++) {
    const p = paragraphs[i];
    const t = getParaText(p).trim();
    if (!t) continue;
    const m = t.match(REF_START_RE);
    if (m) {
      const oldN = parseInt(m[1], 10);
      const newN = mapping[oldN] || oldN;
      const content = m[2];
      const oldPrefix = t.slice(0, t.length - content.length).trim();
      currentBlock = {
        oldN,
        newN,
        oldPrefix,
        primaryP: p,
        paragraphs: [p],
        rest: content,
        m
      };
      blocks.push(currentBlock);
    } else if (currentBlock) {
      currentBlock.paragraphs.push(p);
    }
  }

  if (blocks.length > 0) {
    // Re-number leading digit of each bibliography block
    blocks.forEach(block => {
      const oldPrefix = block.oldPrefix || (block.oldN + ".");
      let newPrefix = (targetStyle === 'ieee') ? `[${block.newN}]` : (targetStyle === 'apa' || targetStyle === 'harvard') ? '' : `${block.newN}.`;
      const p = block.primaryP;
      const tNodes = Array.from(p.getElementsByTagNameNS(W_NS, "t"));

      const v = verdicts[block.oldN] || {};
      let recoveredDoi = null;
      let candidateDoi = (v.recovered_doi || v.doi || '').trim();
      if (!candidateDoi) {
        const refObj = (parsedData.references || []).find(r => r.ref_num === block.oldN);
        if (refObj && refObj.doi) {
          candidateDoi = refObj.doi.trim();
        }
      }
      if (candidateDoi) {
        const cleanKey = candidateDoi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, '').replace(/^doi:\s*/i, '').trim();
        const blockFullText = block.paragraphs.map(bp => 
          Array.from(bp.getElementsByTagNameNS(W_NS, "t")).map(x => x.textContent).join("")
        ).join(" ");
        if (cleanKey && !blockFullText.toLowerCase().includes(cleanKey.toLowerCase())) {
          recoveredDoi = candidateDoi.startsWith("http") ? candidateDoi : (candidateDoi.startsWith("10.") ? `doi: ${candidateDoi}` : `https://doi.org/${cleanKey}`);
        }
      }

      if (trackChanges && block.oldN !== block.newN) {
        let replaced = false;
        // Locate leading run beginning with oldPrefix
        for (const t of tNodes) {
          const tText = t.textContent;
          const trimmed = tText.trimStart();
          if (trimmed.startsWith(oldPrefix)) {
            const indent = tText.substring(0, tText.length - trimmed.length);
            const afterPrefix = trimmed.substring(oldPrefix.length);
            let formattedNewPrefix = newPrefix;
            let formattedAfterPrefix = afterPrefix;
            if (newPrefix && !afterPrefix.startsWith(" ") && !afterPrefix.startsWith("\t")) {
              formattedNewPrefix = newPrefix + " ";
            } else if (!newPrefix) {
              formattedAfterPrefix = afterPrefix.trimStart();
            }
            t.textContent = indent;
            const delEl = createDelRun(xmlDoc, oldPrefix, revCounter++, author, dateStr);
            const insEl = createInsRun(xmlDoc, formattedNewPrefix, revCounter++, author, dateStr);
            const runParent = t.parentNode;
            p.insertBefore(delEl, runParent.nextSibling);
            p.insertBefore(insEl, delEl.nextSibling);
            if (formattedAfterPrefix) {
              const afterRun = xmlDoc.createElementNS(W_NS, "w:r");
              const afterT = xmlDoc.createElementNS(W_NS, "w:t");
              afterT.setAttribute("xml:space", "preserve");
              afterT.textContent = formattedAfterPrefix;
              afterRun.appendChild(afterT);
              p.insertBefore(afterRun, insEl.nextSibling);
            }
            replaced = true;
            break;
          }
        }
        if (!replaced && tNodes.length > 0) {
          const delEl = createDelRun(xmlDoc, `${block.oldN}. `, revCounter++, author, dateStr);
          const insEl = createInsRun(xmlDoc, `${block.newN}. `, revCounter++, author, dateStr);
          // Strict schema compliance: insert AFTER w:pPr if present
          const pPr = p.getElementsByTagNameNS(W_NS, "pPr")[0];
          if (pPr && pPr.nextSibling) {
            p.insertBefore(delEl, pPr.nextSibling);
            p.insertBefore(insEl, delEl.nextSibling);
          } else if (pPr) {
            p.appendChild(delEl);
            p.appendChild(insEl);
          } else {
            p.insertBefore(delEl, p.firstChild);
            p.insertBefore(insEl, delEl.nextSibling);
          }
          tNodes[0].textContent = block.rest;
        }
      } else if (block.oldN !== block.newN) {
        let replaced = false;
        for (const t of tNodes) {
          const tText = t.textContent;
          const trimmed = tText.trimStart();
          if (trimmed.startsWith(oldPrefix)) {
            const indent = tText.substring(0, tText.length - trimmed.length);
            const afterPrefix = trimmed.substring(oldPrefix.length);
            let formattedNewPrefix = newPrefix;
            let formattedAfterPrefix = afterPrefix;
            if (newPrefix && !afterPrefix.startsWith(" ") && !afterPrefix.startsWith("\t")) {
              formattedNewPrefix = newPrefix + " ";
            } else if (!newPrefix) {
              formattedAfterPrefix = afterPrefix.trimStart();
            }
            t.textContent = indent + formattedNewPrefix + formattedAfterPrefix;
            replaced = true;
            break;
          }
        }
        if (!replaced && tNodes.length > 0) {
          tNodes[0].textContent = `${block.newN}. ${block.rest}`;
        }
      }

      if (recoveredDoi) {
        const lastP = block.paragraphs[block.paragraphs.length - 1];
        const sectPr = lastP.getElementsByTagNameNS(W_NS, "sectPr")[0];
        if (trackChanges) {
          const insDoi = createInsRun(xmlDoc, ` ${recoveredDoi}`, revCounter++, author, dateStr);
          if (sectPr) {
            lastP.insertBefore(insDoi, sectPr);
          } else {
            lastP.appendChild(insDoi);
          }
        } else {
          const rDoi = xmlDoc.createElementNS(W_NS, "w:r");
          const tDoi = xmlDoc.createElementNS(W_NS, "w:t");
          tDoi.setAttribute("xml:space", "preserve");
          tDoi.textContent = ` ${recoveredDoi}`;
          rDoi.appendChild(tDoi);
          if (sectPr) {
            lastP.insertBefore(rDoi, sectPr);
          } else {
            lastP.appendChild(rDoi);
          }
        }
      }
    });

    // Reorder atomic reference blocks in the document DOM
    let sortedBlocks = blocks;
    if (styleInfo.sort === "alphabetical") {
      sortedBlocks = [...blocks].sort((a, b) => {
        const refA = (references || []).find(r => r.ref_num === a.oldN);
        const refB = (references || []).find(r => r.ref_num === b.oldN);
        const authA = (refA?.authors?.[0] || a.rest || "").toLowerCase();
        const authB = (refB?.authors?.[0] || b.rest || "").toLowerCase();
        return authA.localeCompare(authB);
      });
    } else if (renumberAma && blocks.length > 1) {
      sortedBlocks = [...blocks].sort((a, b) => a.newN - b.newN);
    }

    if (blocks.length > 0) {
      let currAnchor = null;
      let parentNode = null;

      if (headerIdx >= 0 && headerIdx < paragraphs.length) {
        parentNode = paragraphs[headerIdx].parentNode;
        currAnchor = paragraphs[headerIdx];
      } else {
        parentNode = blocks[0].primaryP.parentNode;
        currAnchor = blocks[0].primaryP.previousElementSibling;
      }

      if (parentNode) {
        sortedBlocks.forEach((b, sIdx) => {
          // Reformat bibliography entry for target style if not AMA
          if (targetStyle !== "ama") {
            const refObj = (references || []).find(r => r.ref_num === b.oldN);
            if (refObj) {
              const formattedLine = formatBibliographyForStyle(targetStyle, sIdx + 1, refObj);
              const oldFull = Array.from(b.primaryP.getElementsByTagNameNS(W_NS, "t")).map(x => x.textContent).join("");
              if (trackChanges && oldFull.trim() !== formattedLine.trim()) {
                const delEl = createDelRun(xmlDoc, oldFull, revCounter++, author, dateStr);
                const insEl = createInsRun(xmlDoc, formattedLine, revCounter++, author, dateStr);
                const pPr = b.primaryP.getElementsByTagNameNS(W_NS, "pPr")[0];
                Array.from(b.primaryP.getElementsByTagNameNS(W_NS, "r")).forEach(r => b.primaryP.removeChild(r));
                if (pPr && pPr.nextSibling) {
                  b.primaryP.insertBefore(delEl, pPr.nextSibling);
                  b.primaryP.insertBefore(insEl, delEl.nextSibling);
                } else {
                  b.primaryP.appendChild(delEl);
                  b.primaryP.appendChild(insEl);
                }
              } else {
                const tNodes = Array.from(b.primaryP.getElementsByTagNameNS(W_NS, "t"));
                if (tNodes.length > 0) {
                  tNodes[0].textContent = formattedLine;
                  for (let ti = 1; ti < tNodes.length; ti++) tNodes[ti].textContent = "";
                }
              }
            }

            if (targetStyle === "apa-7th") {
              let pPr = b.primaryP.getElementsByTagNameNS(W_NS, "pPr")[0];
              if (!pPr) {
                pPr = xmlDoc.createElementNS(W_NS, "w:pPr");
                b.primaryP.insertBefore(pPr, b.primaryP.firstChild);
              }
              let ind = pPr.getElementsByTagNameNS(W_NS, "ind")[0];
              if (!ind) {
                ind = xmlDoc.createElementNS(W_NS, "w:ind");
                pPr.appendChild(ind);
              }
              ind.setAttributeNS(W_NS, "w:left", "720");
              ind.setAttributeNS(W_NS, "w:hanging", "720");
            }
          }

          b.paragraphs.forEach(bp => {
            if (currAnchor) {
              parentNode.insertBefore(bp, currAnchor.nextSibling);
              currAnchor = bp;
            } else {
              parentNode.insertBefore(bp, parentNode.firstChild);
              currAnchor = bp;
            }
          });
        });
      }
    }

    // Inject authentic multi-paragraph ADDIN ZOTERO_BIBL field enclosing all reference blocks
    // Active in BOTH clean mode and track_changes mode
    stripExistingBibliographyFields(xmlDoc);

    const bibHeaderP = (headerIdx >= 0 && headerIdx < paragraphs.length) ? paragraphs[headerIdx] : blocks[0].primaryP;
    if (bibHeaderP) {
      const bibInstr = ' ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} CSL_BIBL {"schema":"https://github.com/citation-style-language/schema/raw/master/csl-bibliography.json","bibliography":{"formattedCitation":"","uncited":[],"omitted":[],"custom":[]}} ';
      const bBegin = createFieldRun(xmlDoc, "begin");
      const bInstr = createFieldRun(xmlDoc, "instr", bibInstr);
      const bSep = createFieldRun(xmlDoc, "separate");

      bibHeaderP.appendChild(bBegin);
      bibHeaderP.appendChild(bInstr);
      bibHeaderP.appendChild(bSep);

      // Locate last reference paragraph
      const lastBlock = (sortedBlocks.length > 0) ? sortedBlocks[sortedBlocks.length - 1] : blocks[blocks.length - 1];
      const lastRefP = lastBlock ? lastBlock.paragraphs[lastBlock.paragraphs.length - 1] : null;

      if (lastRefP) {
        const nextP = lastRefP.nextElementSibling;
        if (nextP && nextP.localName === "p" && !nextP.textContent.trim()) {
          nextP.appendChild(createFieldRun(xmlDoc, "end"));
        } else {
          // Place end at the end of lastRefP (before sectPr if present)
          const sectPr = lastRefP.getElementsByTagNameNS(W_NS, "sectPr")[0];
          const endRun = createFieldRun(xmlDoc, "end");
          if (sectPr) {
            lastRefP.insertBefore(endRun, sectPr);
          } else {
            lastRefP.appendChild(endRun);
          }
        }
      } else {
        bibHeaderP.appendChild(createFieldRun(xmlDoc, "end"));
      }
    }
  }

  // Document Preferences with selected CSL style
  const prefs = {
    styleName: styleName,
    styleId: styleId,
    locale: "en-US",
    libraryID: 1,
    templateVersion: 1,
    purge: false,
    noteStyle: 0,
    bibliographyStyle: 0
  };
  const prefInstr = "ADDIN ZOTERO_PREF_1 " + JSON.stringify(prefs);
  const firstDocP = paragraphs[0];
  if (firstDocP) {
    firstDocP.insertBefore(createFieldRun(xmlDoc, "end"), firstDocP.firstChild);
    firstDocP.insertBefore(createFieldRun(xmlDoc, "separate"), firstDocP.firstChild);
    firstDocP.insertBefore(createFieldRun(xmlDoc, "instr", prefInstr), firstDocP.firstChild);
    firstDocP.insertBefore(createFieldRun(xmlDoc, "begin"), firstDocP.firstChild);
  }

  // Enable Track Changes in word/settings.xml if requested
  if (trackChanges) {
    try {
      let settingsXmlStr = "";
      if (zip.file("word/settings.xml")) {
        settingsXmlStr = await zip.file("word/settings.xml").async("text");
      }
      if (settingsXmlStr) {
        if (!settingsXmlStr.includes("<w:trackRevisions")) {
          settingsXmlStr = settingsXmlStr.replace("</w:settings>", '<w:trackRevisions/></w:settings>');
          zip.file("word/settings.xml", settingsXmlStr);
        }
      } else {
        const newSettings = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:settings xmlns:w="${W_NS}"><w:trackRevisions/></w:settings>`;
        zip.file("word/settings.xml", newSettings);
      }
    } catch (e) {
      console.warn("Could not inject trackRevisions in settings.xml", e);
    }
  }

  // Serialize and repack zip
  const serializer = new XMLSerializer();
  const modifiedXml = serializer.serializeToString(xmlDoc);
  zip.file("word/document.xml", modifiedXml);

  const outBlob = await zip.generateAsync({
    type: "blob",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  });

  return outBlob;
}

