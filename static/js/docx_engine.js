/**
 * In-Browser Docx OOXML Engine & Native Zotero Field Injector
 * Powered by JSZip & browser native XML DOMParser
 */

const W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
const DEFAULT_STYLE = "http://www.zotero.org/styles/american-medical-association";
const DEFAULT_STYLE_NAME = "American Medical Association 11th edition";
const CSL_SCHEMA = "https://github.com/citation-style-language/schema/raw/master/csl-citation.json";

const PAREN_REGEX = /\(((?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?)(?:\s*,\s*(?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?))*)\)/g;
const BRACKET_REGEX = /\[((?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?)(?:\s*,\s*(?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?))*)]/g;
const REF_START_REGEX = /^(\d{1,3})\.\s+(.*)$/;
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

function profileDocumentCitationFormat(paragraphs, paraTexts, scanEnd) {
  let supCount = 0;
  let bracketCount = 0;
  let parenCount = 0;

  for (let pi = 0; pi < Math.min(scanEnd, paragraphs.length); pi++) {
    const pEl = paragraphs[pi];
    const runs = Array.from(pEl.getElementsByTagNameNS(W_NS, "r"));
    let combined = "";
    for (let ri = 0; ri < runs.length; ri++) {
      const r = runs[ri];
      const rText = Array.from(r.getElementsByTagNameNS(W_NS, "t")).map(t => t.textContent).join("");
      const rPr = r.getElementsByTagNameNS(W_NS, "rPr")[0];
      const va = rPr ? rPr.getElementsByTagNameNS(W_NS, "vertAlign")[0] : null;
      const isSup = va && va.getAttributeNS(W_NS, "val") === "superscript";

      if (isSup && /^\d{1,3}(?:[,-]\d{1,3})*$/.test(rText)) {
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
      const inner = bm[1].replace(/–/g, '-');
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
      const inner = pm[1].replace(/–/g, '-');
      const parts = inner.split(/\s*,\s*/).filter(Boolean);
      if (parts.length > 0 && parts.every(p => /^\d{1,3}(?:-\d{1,3})?$/.test(p))) {
        if (parts.some(pt => parseInt(pt.split('-')[0], 10) >= 1900)) continue;
        parenCount++;
      }
    }
  }

  // Dominant format determination
  if (supCount >= 3 && supCount >= bracketCount && (parenCount === 0 || supCount >= 2 * parenCount)) {
    return "sup";
  }
  if (bracketCount >= 3 && bracketCount >= parenCount) {
    return "bracket";
  }
  if (parenCount >= 3 && supCount === 0 && bracketCount === 0) {
    return "paren";
  }
  if (supCount >= 2 && parenCount >= 2) {
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
    const textNodes = p.getElementsByTagNameNS(W_NS, "t");
    return Array.from(textNodes).map(t => t.textContent).join("");
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
    const line = paraTexts[i].trim();
    if (!line) continue;
    // Stop if a post-reference section begins (e.g. Supplementary, Figures, Tables)
    if (refHdrIdx !== -1 && i > refHdrIdx && POST_REF_HEADER_REGEX.test(line) && references.length > 0) {
      break;
    }
    const m = line.match(REF_START_REGEX);
    if (m) {
      const refNum = parseInt(m[1], 10);
      const content = m[2];
      if (isLikelyReferenceLine(content) || (i + 1 < paraTexts.length && (REF_START_REGEX.test(paraTexts[i+1].trim()) && isLikelyReferenceLine(paraTexts[i+1].trim())))) {
        const doiM = content.match(/(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)(10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+)/i) ||
                     content.match(/\b(10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+)\b/);
        const doi = doiM ? doiM[1].replace(/[.,;)]+$/, '') : "";

        const parts = content.split(". ");
        const authors = parts.length > 0 ? parts[0].split(/,| and /).map(a => a.trim()).filter(Boolean) : [];
        const title = parts.length > 1 ? parts[1].trim() : "";

        references.push({
          ref_num: refNum,
          raw_text: line,
          title: title,
          authors: authors,
          journal: "",
          year: "",
          volume: "",
          issue: "",
          pages: "",
          doi: doi
        });
      }
    } else if (references.length > 0) {
      // Check multi-line reference continuation (e.g. wrapped DOI or PMID on subsequent paragraph)
      const contDoiM = line.match(/(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)(10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+)/i) ||
                        line.match(/\b(10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+)\b/);
      if (contDoiM) {
        const lastRef = references[references.length - 1];
        lastRef.raw_text += " " + line;
        if (!lastRef.doi) {
          lastRef.doi = contDoiM[1].replace(/[.,;)]+$/, '');
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
  const maxRefNum = references.length > 0 ? references.length : 999;

  for (let pi = bodyStart; pi < scanEnd; pi++) {
    const pEl = paragraphs[pi];
    const pText = paraTexts[pi];
    if (!pText.trim()) continue;

    const runs = Array.from(pEl.getElementsByTagNameNS(W_NS, "r")).filter(r => !r.closest("w\\:del, del"));
    let combinedPrev = "";

    for (let ri = 0; ri < runs.length; ri++) {
      const r = runs[ri];
      const rText = Array.from(r.getElementsByTagNameNS(W_NS, "t")).map(t => t.textContent).join("");
      
      // Check superscript
      const rPr = r.getElementsByTagNameNS(W_NS, "rPr")[0];
      const va = rPr ? rPr.getElementsByTagNameNS(W_NS, "vertAlign")[0] : null;
      const isSup = va && va.getAttributeNS(W_NS, "val") === "superscript";

      // 1. Superscript check
      if ((effectiveFormat === "auto" || effectiveFormat === "sup" || effectiveFormat === "mixed") && isSup && /^\d{1,3}(?:[,-]\d{1,3})*$/.test(rText)) {
        const inner = rText.replace(/–/g, '-');
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
            sites.push({
              paragraph_idx: pi,
              run_idx: ri,
              kind: "sup",
              text: rText,
              context_before: combinedPrev.slice(-40),
              sentence: pText.slice(0, 120),
              nums: Array.from(new Set(nums)).sort((a,b) => a - b)
            });
          }
        }
      }

      // 2. Square Bracket match [1, 2]
      if (effectiveFormat === "auto" || effectiveFormat === "bracket") {
        let bMatch;
        const bracketRe = new RegExp(BRACKET_REGEX);
        while ((bMatch = bracketRe.exec(rText)) !== null) {
          const contextPrior = (combinedPrev + rText.slice(0, bMatch.index)).trim();
          if (NON_CITATION_PRECEDING_WORDS.test(contextPrior) || CLINICAL_SCALE_REGEX.test(contextPrior.slice(-60))) {
            continue;
          }
          if (NON_CITATION_INNER_CONTENT.test(bMatch[0].slice(1, -1))) {
            continue;
          }

          const inner = bMatch[1].replace(/–/g, '-');
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
            sites.push({
              paragraph_idx: pi,
              run_idx: ri,
              kind: "bracket",
              text: bMatch[0],
              context_before: pText.slice(Math.max(0, bMatch.index - 40), bMatch.index),
              sentence: pText.slice(0, 140),
              nums: Array.from(new Set(nums)).sort((a,b) => a - b),
              match_start: bMatch.index,
              match_end: bMatch.index + bMatch[0].length
            });
          }
        }
      }

      // 3. Parenthetical match (1, 2)
      if (effectiveFormat === "auto" || effectiveFormat === "paren" || effectiveFormat === "mixed") {
        let match;
        const parenRe = new RegExp(PAREN_REGEX);
        while ((match = parenRe.exec(rText)) !== null) {
          // Check clinical nouns and clinical scale lookbehind
          const contextPrior = (combinedPrev + rText.slice(0, match.index)).trim();
          if (NON_CITATION_PRECEDING_WORDS.test(contextPrior) || CLINICAL_SCALE_REGEX.test(contextPrior.slice(-60))) {
            continue;
          }
          if (NON_CITATION_INNER_CONTENT.test(match[0].slice(1, -1))) {
            continue;
          }
          // Check enumerated list start
          const trailing = rText.slice(match.index, match.index + match[0].length + 20);
          if (ENUMERATED_LIST_START.test(trailing) && !contextPrior) {
            continue;
          }

          const inner = match[1].replace(/–/g, '-');
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
            sites.push({
              paragraph_idx: pi,
              run_idx: ri,
              kind: "paren",
              text: match[0],
              context_before: pText.slice(Math.max(0, match.index - 40), match.index),
              sentence: pText.slice(0, 140),
              nums: Array.from(new Set(nums)).sort((a,b) => a - b),
              match_start: match.index,
              match_end: match.index + match[0].length
            });
          }
        }
      }
      combinedPrev += rText;
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

function createDelRun(doc, text, revId, author = "Co-Scientist", dateStr = null, isSuperscript = false) {
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

function createInsRun(doc, text, revId, author = "Co-Scientist", dateStr = null, isSuperscript = false) {
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

function appendAuditLedgerToDocx(xmlDoc, parsedData, verdicts, amaMapping) {
  const references = parsedData.references || [];
  if (references.length === 0) return;

  const body = xmlDoc.getElementsByTagNameNS(W_NS, "body")[0];
  if (!body) return;

  const bodySectPr = Array.from(body.childNodes).find(n => n.nodeType === 1 && n.localName === "sectPr");

  function insertNode(node) {
    if (bodySectPr) {
      body.insertBefore(node, bodySectPr);
    } else {
      body.appendChild(node);
    }
  }

  // Heading paragraph
  const pHead = xmlDoc.createElementNS(W_NS, "w:p");
  const pPrHead = xmlDoc.createElementNS(W_NS, "w:pPr");
  const spHead = xmlDoc.createElementNS(W_NS, "w:spacing");
  spHead.setAttributeNS(W_NS, "w:before", "480");
  spHead.setAttributeNS(W_NS, "w:after", "120");
  pPrHead.appendChild(spHead);
  pHead.appendChild(pPrHead);

  const rHead = xmlDoc.createElementNS(W_NS, "w:r");
  const rPrHead = xmlDoc.createElementNS(W_NS, "w:rPr");
  const bHead = xmlDoc.createElementNS(W_NS, "w:b");
  const szHead = xmlDoc.createElementNS(W_NS, "w:sz");
  szHead.setAttributeNS(W_NS, "w:val", "26"); // 13pt
  const colorHead = xmlDoc.createElementNS(W_NS, "w:color");
  colorHead.setAttributeNS(W_NS, "w:val", "3A0F34");
  rPrHead.appendChild(bHead);
  rPrHead.appendChild(szHead);
  rPrHead.appendChild(colorHead);
  rHead.appendChild(rPrHead);

  const tHead = xmlDoc.createElementNS(W_NS, "w:t");
  tHead.textContent = "Co-Scientist Reference Audit & Reachability Ledger";
  rHead.appendChild(tHead);
  pHead.appendChild(rHead);
  insertNode(pHead);

  // Subtitle paragraph
  const pSub = xmlDoc.createElementNS(W_NS, "w:p");
  const pPrSub = xmlDoc.createElementNS(W_NS, "w:pPr");
  const spSub = xmlDoc.createElementNS(W_NS, "w:spacing");
  spSub.setAttributeNS(W_NS, "w:after", "240");
  pPrSub.appendChild(spSub);
  pSub.appendChild(pPrSub);

  const rSub = xmlDoc.createElementNS(W_NS, "w:r");
  const rPrSub = xmlDoc.createElementNS(W_NS, "w:rPr");
  const iSub = xmlDoc.createElementNS(W_NS, "w:i");
  const szSub = xmlDoc.createElementNS(W_NS, "w:sz");
  szSub.setAttributeNS(W_NS, "w:val", "19"); // 9.5pt
  const colorSub = xmlDoc.createElementNS(W_NS, "w:color");
  colorSub.setAttributeNS(W_NS, "w:val", "62535D");
  rPrSub.appendChild(iSub);
  rPrSub.appendChild(szSub);
  rPrSub.appendChild(colorSub);
  rSub.appendChild(rPrSub);

  const tSub = xmlDoc.createElementNS(W_NS, "w:t");
  tSub.textContent = `Independent scholarly verification across Crossref, DOI Foundation Handle Registry, Europe PMC, and OpenAlex. Audited ${references.length} bibliography references. Formatted for peer review verification.`;
  rSub.appendChild(tSub);
  pSub.appendChild(rSub);
  insertNode(pSub);

  // Table
  const tbl = xmlDoc.createElementNS(W_NS, "w:tbl");
  const tblPr = xmlDoc.createElementNS(W_NS, "w:tblPr");
  const tblW = xmlDoc.createElementNS(W_NS, "w:tblW");
  tblW.setAttributeNS(W_NS, "w:w", "5000");
  tblW.setAttributeNS(W_NS, "w:type", "pct");
  tblPr.appendChild(tblW);

  // Borders
  const tblBorders = xmlDoc.createElementNS(W_NS, "w:tblBorders");
  ["top", "left", "bottom", "right", "insideH", "insideV"].forEach(side => {
    const b = xmlDoc.createElementNS(W_NS, `w:${side}`);
    b.setAttributeNS(W_NS, "w:val", "single");
    b.setAttributeNS(W_NS, "w:sz", "4");
    b.setAttributeNS(W_NS, "w:space", "0");
    b.setAttributeNS(W_NS, "w:color", "D2C2CB");
    tblBorders.appendChild(b);
  });
  tblPr.appendChild(tblBorders);
  tbl.appendChild(tblPr);

  // Table Grid (<w:tblGrid> required by ISO/IEC 29500-1 schema)
  const tblGrid = xmlDoc.createElementNS(W_NS, "w:tblGrid");
  const colTitles = ["#", "Bibliographic Record", "DOI Identifier", "Audit Status", "Citations"];
  const colWidths = ["800", "4200", "2200", "1800", "1000"];
  colWidths.forEach(w => {
    const gridCol = xmlDoc.createElementNS(W_NS, "w:gridCol");
    gridCol.setAttributeNS(W_NS, "w:w", w);
    tblGrid.appendChild(gridCol);
  });
  tbl.appendChild(tblGrid);

  // Table Header Row
  const trHdr = xmlDoc.createElementNS(W_NS, "w:tr");

  colTitles.forEach((title, idx) => {
    const tc = xmlDoc.createElementNS(W_NS, "w:tc");
    const tcPr = xmlDoc.createElementNS(W_NS, "w:tcPr");
    const tcW = xmlDoc.createElementNS(W_NS, "w:tcW");
    tcW.setAttributeNS(W_NS, "w:w", colWidths[idx]);
    tcW.setAttributeNS(W_NS, "w:type", "dxa");
    tcPr.appendChild(tcW);

    const shd = xmlDoc.createElementNS(W_NS, "w:shd");
    shd.setAttributeNS(W_NS, "w:val", "clear");
    shd.setAttributeNS(W_NS, "w:color", "auto");
    shd.setAttributeNS(W_NS, "w:fill", "3A0F34");
    tcPr.appendChild(shd);
    tc.appendChild(tcPr);

    const p = xmlDoc.createElementNS(W_NS, "w:p");
    const r = xmlDoc.createElementNS(W_NS, "w:r");
    const rPr = xmlDoc.createElementNS(W_NS, "w:rPr");
    const b = xmlDoc.createElementNS(W_NS, "w:b");
    const clr = xmlDoc.createElementNS(W_NS, "w:color");
    clr.setAttributeNS(W_NS, "w:val", "FFFFFF");
    const sz = xmlDoc.createElementNS(W_NS, "w:sz");
    sz.setAttributeNS(W_NS, "w:val", "18");
    rPr.appendChild(b);
    rPr.appendChild(clr);
    rPr.appendChild(sz);
    r.appendChild(rPr);

    const t = xmlDoc.createElementNS(W_NS, "w:t");
    t.textContent = title;
    r.appendChild(t);
    p.appendChild(r);
    tc.appendChild(p);
    trHdr.appendChild(tc);
  });
  tbl.appendChild(trHdr);

  // Data rows
  const sortedRefs = [...references];
  if (amaMapping) {
    sortedRefs.sort((a, b) => (amaMapping[a.ref_num] || a.ref_num) - (amaMapping[b.ref_num] || b.ref_num));
  }

  sortedRefs.forEach(rItem => {
    const oldN = rItem.ref_num;
    const newN = (amaMapping && amaMapping[oldN]) || oldN;
    const v = verdicts[oldN] || {};
    const doiVal = v.recovered_doi || v.doi || rItem.doi || "";

    let statusText = "Verified";
    if (v.is_recovered || v.status === "recovered") {
      statusText = "DOI Recovered";
    } else if (v.is_bot_gated || v.status === "bot_protected") {
      statusText = "Bot Gated / Paywall";
    } else if (v.is_reachable || v.status === "verified") {
      statusText = "Verified Live (200 OK)";
    } else if (v.status === "unreachable") {
      statusText = "Unreachable (404)";
    } else if (!doiVal) {
      statusText = "Missing DOI";
    }

    const tr = xmlDoc.createElementNS(W_NS, "w:tr");
    const recTitle = v.crossref_title || rItem.title || rItem.raw_text.slice(0, 80);
    const numDisplay = (newN === oldN) ? `[${newN}]` : `[${newN}] (Orig ${oldN})`;
    const citCount = (parsedData.sites || []).filter(s => (s.nums || []).includes(oldN)).length;

    const rowData = [numDisplay, recTitle, doiVal || "None", statusText, `${citCount}x`];

    rowData.forEach((val, idx) => {
      const tc = xmlDoc.createElementNS(W_NS, "w:tc");
      const tcPr = xmlDoc.createElementNS(W_NS, "w:tcPr");
      const tcW = xmlDoc.createElementNS(W_NS, "w:tcW");
      tcW.setAttributeNS(W_NS, "w:w", colWidths[idx]);
      tcW.setAttributeNS(W_NS, "w:type", "dxa");
      tcPr.appendChild(tcW);
      tc.appendChild(tcPr);

      const p = xmlDoc.createElementNS(W_NS, "w:p");
      const r = xmlDoc.createElementNS(W_NS, "w:r");
      const rPr = xmlDoc.createElementNS(W_NS, "w:rPr");
      const clr = xmlDoc.createElementNS(W_NS, "w:color");
      clr.setAttributeNS(W_NS, "w:val", "4F444B");
      const sz = xmlDoc.createElementNS(W_NS, "w:sz");
      sz.setAttributeNS(W_NS, "w:val", "17"); // 8.5pt
      rPr.appendChild(clr);
      rPr.appendChild(sz);
      r.appendChild(rPr);

      const t = xmlDoc.createElementNS(W_NS, "w:t");
      t.textContent = val;
      r.appendChild(t);
      p.appendChild(r);
      tc.appendChild(p);
      tr.appendChild(tc);
    });

    tbl.appendChild(tr);
  });

  insertNode(tbl);
}

export async function injectZoteroFieldsInBrowser(
  parsedData,
  verdicts = {},
  renumberAma = true,
  trackChanges = false,
  author = "Co-Scientist",
  includeAuditLedger = true
) {
  const { zip, xmlDoc, paragraphs, sites, references } = parsedData;
  let revCounter = 1;
  const dateStr = new Date().toISOString();

  // Determine AMA sequential re-numbering map
  let mapping = {};
  if (renumberAma) {
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

    // Ensure run has superscript formatting
    let rPr = targetRun.getElementsByTagNameNS(W_NS, "rPr")[0];
    if (!rPr) {
      rPr = xmlDoc.createElementNS(W_NS, "w:rPr");
      targetRun.insertBefore(rPr, targetRun.firstChild);
    }
    let va = rPr.getElementsByTagNameNS(W_NS, "vertAlign")[0];
    if (!va) {
      va = xmlDoc.createElementNS(W_NS, "w:vertAlign");
      va.setAttributeNS(W_NS, "w:val", "superscript");
      rPr.appendChild(va);
    }

    // Format new numbers with AMA range condensation
    const newSiteNums = Array.from(new Set(site.nums.map(n => mapping[n] || n))).sort((a,b) => a - b);
    const condensedStr = formatCondensedCitation(newSiteNums);
    const tNodes = targetRun.getElementsByTagNameNS(W_NS, "t");
    const oldText = (tNodes.length > 0) ? tNodes[0].textContent : site.text;

    let targetAnchor = targetRun;

    if (trackChanges && oldText !== condensedStr) {
      const delEl = createDelRun(xmlDoc, oldText, revCounter++, author, dateStr, site.kind === "sup");
      const insEl = createInsRun(xmlDoc, condensedStr, revCounter++, author, dateStr, true);
      p.insertBefore(delEl, targetRun);
      p.insertBefore(insEl, targetRun);
      p.removeChild(targetRun);
      targetAnchor = insEl;
    } else {
      if (tNodes.length > 0) {
        tNodes[0].textContent = condensedStr;
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
        formattedCitation: condensedStr,
        plainCitation: condensedStr,
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

    p.insertBefore(rBegin, targetAnchor);
    p.insertBefore(rInstr, targetAnchor);
    p.insertBefore(rSep, targetAnchor);
    if (targetAnchor.nextSibling) {
      p.insertBefore(rEnd, targetAnchor.nextSibling);
    } else {
      p.appendChild(rEnd);
    }
  }

  // Boundary Isolation & Atomic Reference Blocks
  const REF_HEADER_RE = /^\s*(?:REFERENCES|Reference List|Bibliography|Works Cited)\s*$/i;
  const POST_REF_HEADER_RE = /^\s*(?:Supplementary\s+|Supplemental\s+|Appendix\b|Appendices\b|Tables?\b|Figure\s+Legends?|Figures?\b|Author\s+Contributions|Funding\b|Conflict(?:s)?\s+of\s+Interest|IRB\s+Statement|Informed\s+Consent)/i;
  const REF_START_RE = /^(\d{1,3})\.\s*(.*)$/;

  let headerIdx = -1;
  let startIdx = -1;
  let endIdx = -1;

  for (let i = 0; i < paragraphs.length; i++) {
    const t = Array.from(paragraphs[i].getElementsByTagNameNS(W_NS, "t")).map(x => x.textContent).join("").trim();
    if (REF_HEADER_RE.test(t)) {
      headerIdx = i;
      startIdx = i + 1;
      break;
    }
  }

  if (startIdx === -1) {
    for (let i = 0; i < paragraphs.length; i++) {
      const t = Array.from(paragraphs[i].getElementsByTagNameNS(W_NS, "t")).map(x => x.textContent).join("").trim();
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
      const t = Array.from(paragraphs[i].getElementsByTagNameNS(W_NS, "t")).map(x => x.textContent).join("").trim();
      if (POST_REF_HEADER_RE.test(t)) {
        endIdx = i;
        break;
      }
    }
    if (endIdx === -1) endIdx = paragraphs.length;
  }

  // Extract atomic reference blocks within [startIdx, endIdx)
  const blocks = [];
  let currentBlock = null;

  for (let i = startIdx; i < endIdx; i++) {
    const p = paragraphs[i];
    const t = Array.from(p.getElementsByTagNameNS(W_NS, "t")).map(x => x.textContent).join("").trim();
    if (!t) continue;
    const m = t.match(REF_START_RE);
    if (m) {
      const oldN = parseInt(m[1], 10);
      const newN = mapping[oldN] || oldN;
      currentBlock = {
        oldN,
        newN,
        primaryP: p,
        paragraphs: [p],
        rest: m[2],
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
      const oldPrefix = block.oldN + ".";
      const newPrefix = block.newN + ".";
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
            t.textContent = indent;
            const delEl = createDelRun(xmlDoc, oldPrefix, revCounter++, author, dateStr);
            const insEl = createInsRun(xmlDoc, newPrefix, revCounter++, author, dateStr);
            const runParent = t.parentNode;
            p.insertBefore(delEl, runParent.nextSibling);
            p.insertBefore(insEl, delEl.nextSibling);
            if (afterPrefix) {
              const afterRun = xmlDoc.createElementNS(W_NS, "w:r");
              const afterT = xmlDoc.createElementNS(W_NS, "w:t");
              afterT.setAttribute("xml:space", "preserve");
              afterT.textContent = afterPrefix;
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
            t.textContent = indent + newPrefix + afterPrefix;
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
    if (renumberAma && blocks.length > 1) {
      const sortedBlocks = [...blocks].sort((a, b) => a.newN - b.newN);
      let anchorNode = null;
      let parentNode = null;

      if (headerIdx >= 0 && headerIdx < paragraphs.length) {
        parentNode = paragraphs[headerIdx].parentNode;
        anchorNode = paragraphs[headerIdx].nextSibling;
      } else {
        parentNode = blocks[0].primaryP.parentNode;
        anchorNode = blocks[0].primaryP;
      }

      if (parentNode) {
        sortedBlocks.forEach(b => {
          b.paragraphs.forEach(bp => {
            parentNode.insertBefore(bp, anchorNode);
          });
        });
      }
    }

    // In clean mode only: inject self-contained ADDIN ZOTERO_BIBL field marker on REFERENCES header
    if (!trackChanges) {
      const bibHeaderP = (headerIdx >= 0 && headerIdx < paragraphs.length) ? paragraphs[headerIdx] : blocks[0].primaryP;
      if (bibHeaderP) {
        const bibInstr = 'ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} CSL_BIBLIOGRAPHY';
        const bBegin = createFieldRun(xmlDoc, "begin");
        const bInstr = createFieldRun(xmlDoc, "instr", bibInstr);
        const bSep = createFieldRun(xmlDoc, "separate");
        const bEnd = createFieldRun(xmlDoc, "end");

        bibHeaderP.appendChild(bBegin);
        bibHeaderP.appendChild(bInstr);
        bibHeaderP.appendChild(bSep);
        bibHeaderP.appendChild(bEnd);
      }
    }
  }

  // Document Preferences (AMA 11th edition)
  const prefs = {
    styleName: DEFAULT_STYLE_NAME,
    styleId: DEFAULT_STYLE,
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

  // Append Co-Scientist Reference Audit & Reachability Ledger Table
  if (includeAuditLedger && references && references.length > 0) {
    appendAuditLedgerToDocx(xmlDoc, parsedData, verdicts, mapping);
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

