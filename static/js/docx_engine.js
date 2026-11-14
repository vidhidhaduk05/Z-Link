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
const CLASSIFICATION_NOUNS = /\b(case|stage|grade|type|group|cohort|sample|patient|day|step|table|fig|figure|equation|eq|formula|model)\s*$/i;
const CLINICAL_SCALE_REGEX = /\b(graded\s+(?:on|as|by)?|scores?|scales?|grades?|grading|stages?|staging|classes?|indices?|index|points?|severity|levels?|subscores?|criteria|systems?|angiography|perfusion|tomography|mRS|NIHSS|GCS|mTICI|TICI|TIMI|ASPECTS|DSA)\b/i;
const ENUMERATED_LIST_START = /^\s*\((?:\d{1,2})\)\s+[A-Z]/;

function isLikelyReferenceLine(line) {
  const clean = (line || "").trim();
  if (!clean) return false;
  if (/(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+/i.test(clean) ||
      /\b(10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+)\b/.test(clean) ||
      /PMID:\s*\d{6,9}/i.test(clean)) {
    return true;
  }
  if (YEAR_REGEX.test(clean)) return true;
  if (clean.toLowerCase().includes('et al') || clean.includes(';') || clean.includes(':')) return true;
  const words = clean.split(/\s+/);
  if (words.length <= 6) return false;
  return true;
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
    const bMatches = pText.match(BRACKET_REGEX) || [];
    bMatches.forEach(b => {
      const inner = b.slice(1, -1).replace(/–/g, '-');
      const parts = inner.split(/\s*,\s*/).filter(Boolean);
      if (parts.length > 0 && parts.every(p => /^\d{1,3}(?:-\d{1,3})?$/.test(p))) {
        bracketCount++;
      }
    });

    // Parens (applying clinical scale guards)
    const pMatches = pText.match(PAREN_REGEX) || [];
    pMatches.forEach(pm => {
      const inner = pm.slice(1, -1).replace(/–/g, '-');
      const parts = inner.split(/\s*,\s*/).filter(Boolean);
      if (parts.length > 0 && parts.every(p => /^\d{1,3}(?:-\d{1,3})?$/.test(p))) {
        parenCount++;
      }
    });
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

export async function parseDocxFile(fileOrBuffer, citationFormat = "auto") {
  if (!window.JSZip) {
    throw new Error("JSZip library not loaded.");
  }

  const zip = await window.JSZip.loadAsync(fileOrBuffer);
  const docXmlStr = await zip.file("word/document.xml").async("text");
  
  const parser = new DOMParser();
  const xmlDoc = parser.parseFromString(docXmlStr, "application/xml");
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
      if (isLikelyReferenceLine(content) || (i + 1 < paraTexts.length && (REF_START_REGEX.test(paraTexts[i+1].trim()) || /(?:https?:\/\/|doi:)/i.test(paraTexts[i+1])))) {
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

    const runs = Array.from(pEl.getElementsByTagNameNS(W_NS, "r"));
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
          if (Math.max(...nums) <= maxRefNum) {
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

          if (nums.length > 0 && Math.max(...nums) <= maxRefNum) {
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
          // Check classification nouns and clinical scale lookbehind
          const contextPrior = (combinedPrev + rText.slice(0, match.index)).trim();
          if (CLASSIFICATION_NOUNS.test(contextPrior)) {
            continue;
          }
          if (CLINICAL_SCALE_REGEX.test(contextPrior.slice(-60))) {
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

          if (nums.length > 0 && Math.max(...nums) <= maxRefNum) {
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

export async function injectZoteroFieldsInBrowser(parsedData, verdicts = {}) {
  const { zip, xmlDoc, paragraphs, sites, references } = parsedData;

  const cslMap = {};
  for (const ref of references) {
    const v = verdicts[ref.ref_num] || {};
    const title = v.crossref_title || ref.title || "Article";
    const journal = v.crossref_journal || ref.journal || "";
    const year = v.crossref_year || ref.year || "2020";
    const authors = (v.crossref_authors && v.crossref_authors.length > 0) ? v.crossref_authors : (ref.authors || ["Author"]);
    
    cslMap[ref.ref_num] = {
      id: `ITEM-${ref.ref_num}`,
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

    // Format plain numbers (e.g. "1,2")
    const numStr = site.nums.join(",");
    const tNodes = targetRun.getElementsByTagNameNS(W_NS, "t");
    if (tNodes.length > 0) {
      tNodes[0].textContent = numStr;
    }

    const citationItems = site.nums.map(n => ({
      id: `zotero_key_${n}`,
      uris: [`http://zotero.org/users/0/items/zotero_key_${n}`],
      itemData: cslMap[n] || {}
    }));

    const citationJson = {
      citationID: Math.random().toString(36).substring(2, 10),
      properties: {
        formattedCitation: numStr,
        plainCitation: numStr,
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

    p.insertBefore(rBegin, targetRun);
    p.insertBefore(rInstr, targetRun);
    p.insertBefore(rSep, targetRun);
    if (targetRun.nextSibling) {
      p.insertBefore(rEnd, targetRun.nextSibling);
    } else {
      p.appendChild(rEnd);
    }
  }

  // Bibliography wrapper
  const refParas = paragraphs.filter(p => {
    const t = Array.from(p.getElementsByTagNameNS(W_NS, "t")).map(x => x.textContent).join("").trim();
    return /^\d{1,3}\.\s/.test(t);
  });

  if (refParas.length > 0) {
    const firstP = refParas[0];
    const lastP = refParas[refParas.length - 1];

    const bibInstr = 'ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} CSL_BIBLIOGRAPHY';
    const bBegin = createFieldRun(xmlDoc, "begin");
    const bInstr = createFieldRun(xmlDoc, "instr", bibInstr);
    const bSep = createFieldRun(xmlDoc, "separate");
    const bEnd = createFieldRun(xmlDoc, "end");

    firstP.insertBefore(bSep, firstP.firstChild);
    firstP.insertBefore(bInstr, firstP.firstChild);
    firstP.insertBefore(bBegin, firstP.firstChild);
    lastP.appendChild(bEnd);
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

