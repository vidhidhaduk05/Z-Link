/**
 * In-Browser Docx OOXML Engine & Native Zotero Field Injector
 * Powered by JSZip & browser native XML DOMParser
 */

const W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
const DEFAULT_STYLE = "http://www.zotero.org/styles/american-medical-association";
const DEFAULT_STYLE_NAME = "American Medical Association 11th edition";
const CSL_SCHEMA = "https://github.com/citation-style-language/schema/raw/master/csl-citation.json";

const PAREN_REGEX = /\(((?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?)(?:\s*,\s*(?:\d{1,3}(?:\s*[-–]\s*\d{1,3})?))*)\)/g;
const REF_START_REGEX = /^(\d{1,3})\.\s+(.*)$/;
const REF_HEADER_REGEX = /^(REFERENCES|Reference List|Bibliography|Works Cited)\s*$/i;
const BODY_START_REGEX = /^(ABSTRACT|SUMMARY STATEMENT|INTRODUCTION|BACKGROUND|Key Results)\s*$/i;

export async function parseDocxFile(fileOrBuffer) {
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
    const m = line.match(REF_START_REGEX);
    if (m) {
      const refNum = parseInt(m[1], 10);
      const content = m[2];
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

      if (isSup && /^\d{1,3}(?:[,-]\d{1,3})*$/.test(rText)) {
        const nums = rText.split(/[,-]/).map(x => parseInt(x, 10)).filter(x => !isNaN(x));
        const prevChar = combinedPrev.slice(-1);
        if (prevChar && !/\d/.test(prevChar) && !/[RrχτIβ]/.test(prevChar)) {
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
      } else {
        // Parenthetical match
        let match;
        const parenRe = new RegExp(PAREN_REGEX);
        while ((match = parenRe.exec(rText)) !== null) {
          const inner = match[1].replace(/–/g, '-');
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
    refHdrIdx
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
