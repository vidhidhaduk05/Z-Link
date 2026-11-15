/**
 * CSL Citation & Bibliography Formatter Engine
 * Provides native Zotero-compatible citation style switching across:
 * - AMA 11th Edition (Superscript, Sequential)
 * - Vancouver (Square Brackets [1, 2] & Parentheses (1, 2), Sequential)
 * - IEEE (Bracketed [1], Sequential)
 * - Nature (Superscript, Author-First Compact)
 * - APA 7th Edition (Author-Date (Smith et al., 2020), Alphabetical)
 * - Harvard (Author-Date (Smith & Doe, 2020), Alphabetical)
 */

export const CSL_STYLES = {
  // --- Major Radiology Journals (RSNA, ASNR, ARRS, ESR, SIR, ACR) ---
  "radiology": {
    id: "http://www.zotero.org/styles/radiology",
    name: "Radiology (RSNA)",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },
  "ajnr": {
    id: "http://www.zotero.org/styles/american-journal-of-neuroradiology",
    name: "American Journal of Neuroradiology (AJNR)",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },
  "ajr": {
    id: "http://www.zotero.org/styles/american-journal-of-roentgenology",
    name: "American Journal of Roentgenology (AJR)",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },
  "european-radiology": {
    id: "http://www.zotero.org/styles/european-radiology",
    name: "European Radiology (ESR / Springer)",
    category: "numeric",
    inTextKind: "bracket",
    sort: "sequential"
  },
  "radiographics": {
    id: "http://www.zotero.org/styles/radiographics",
    name: "RadioGraphics (RSNA)",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },
  "jvir": {
    id: "http://www.zotero.org/styles/journal-of-vascular-and-interventional-radiology",
    name: "Journal of Vascular and Interventional Radiology (JVIR)",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },
  "jacr": {
    id: "http://www.zotero.org/styles/journal-of-the-american-college-of-radiology",
    name: "Journal of the American College of Radiology (JACR)",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },
  "investigative-radiology": {
    id: "http://www.zotero.org/styles/investigative-radiology",
    name: "Investigative Radiology (LWW)",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },
  "academic-radiology": {
    id: "http://www.zotero.org/styles/academic-radiology",
    name: "Academic Radiology (Elsevier)",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },
  "clinical-radiology": {
    id: "http://www.zotero.org/styles/clinical-radiology",
    name: "Clinical Radiology (RCR / Elsevier)",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },
  "korean-journal-of-radiology": {
    id: "http://www.zotero.org/styles/korean-journal-of-radiology",
    name: "Korean Journal of Radiology (KJR)",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },
  "cvir": {
    id: "http://www.zotero.org/styles/cardiovascular-and-interventional-radiology",
    name: "CardioVascular and Interventional Radiology (CVIR)",
    category: "numeric",
    inTextKind: "bracket",
    sort: "sequential"
  },
  "pediatric-radiology": {
    id: "http://www.zotero.org/styles/pediatric-radiology",
    name: "Pediatric Radiology (Springer)",
    category: "numeric",
    inTextKind: "bracket",
    sort: "sequential"
  },
  "journal-of-nuclear-medicine": {
    id: "http://www.zotero.org/styles/journal-of-nuclear-medicine",
    name: "Journal of Nuclear Medicine (JNM / SNMMI)",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },

  // --- General Medical & Scientific Numeric Styles ---
  "ama": {
    id: "http://www.zotero.org/styles/american-medical-association",
    name: "American Medical Association 11th edition",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },
  "vancouver-bracket": {
    id: "http://www.zotero.org/styles/vancouver",
    name: "Vancouver (Square Brackets)",
    category: "numeric",
    inTextKind: "bracket",
    sort: "sequential"
  },
  "vancouver-paren": {
    id: "http://www.zotero.org/styles/vancouver-brackets-parentheses",
    name: "Vancouver (Parentheses)",
    category: "numeric",
    inTextKind: "paren",
    sort: "sequential"
  },
  "ieee": {
    id: "http://www.zotero.org/styles/ieee",
    name: "IEEE",
    category: "numeric",
    inTextKind: "bracket",
    sort: "sequential"
  },
  "nature": {
    id: "http://www.zotero.org/styles/nature",
    name: "Nature",
    category: "numeric",
    inTextKind: "sup",
    sort: "sequential"
  },

  // --- Author-Date Styles ---
  "apa-7th": {
    id: "http://www.zotero.org/styles/apa",
    name: "American Psychological Association 7th edition",
    category: "author-date",
    inTextKind: "author-date",
    sort: "alphabetical"
  },
  "harvard": {
    id: "http://www.zotero.org/styles/harvard-cite-them-right",
    name: "Harvard (Cite Them Right)",
    category: "author-date",
    inTextKind: "author-date",
    sort: "alphabetical"
  }
};

/**
 * Parse author string or array into structured {family, given} items
 */
export function parseAuthorNames(authorsInput) {
  if (!authorsInput) return [];
  const authorList = Array.isArray(authorsInput)
    ? authorsInput
    : authorsInput.split(/\s*,\s*|\s+and\s+/);

  const PARTICLES = new Set(['van', 'von', 'de', 'del', 'da', 'di', 'du', 'la', 'le', 'der', 'den', 'ter', 'mc', 'mac']);
  const parsed = [];
  for (let raw of authorList) {
    let clean = (raw || "").trim().replace(/[.,;]+$/, "");
    if (!clean || clean.toLowerCase() === "et al") continue;

    if (clean.includes(",")) {
      const parts = clean.split(",");
      parsed.push({
        family: parts[0].trim(),
        given: parts[1] ? parts[1].trim() : ""
      });
      continue;
    }

    const parts = clean.split(/\s+/);
    if (parts.length === 1) {
      parsed.push({ family: parts[0], given: "" });
      continue;
    }

    let pIdx = 0;
    while (pIdx < parts.length - 1 && PARTICLES.has(parts[pIdx].toLowerCase())) {
      pIdx++;
    }
    const familyWords = parts.slice(0, pIdx + 1);
    const givenWords = parts.slice(pIdx + 1);

    if (givenWords.length > 0) {
      parsed.push({
        family: familyWords.join(" "),
        given: givenWords.join(" ")
      });
    } else {
      parsed.push({
        family: familyWords[0],
        given: familyWords.slice(1).join(" ")
      });
    }
  }
  return parsed;
}

/**
 * Condense consecutive numbers: [1, 2, 3, 5] -> "1-3,5"
 */
export function condenseNumericRanges(nums) {
  if (!nums || nums.length === 0) return "";
  const unique = Array.from(new Set(nums.map(n => parseInt(n, 10)).filter(n => !isNaN(n)))).sort((a, b) => a - b);
  if (unique.length === 0) return "";

  const ranges = [];
  let start = unique[0];
  let prev = start;

  for (let i = 1; i < unique.length; i++) {
    const cur = unique[i];
    if (cur === prev + 1) {
      prev = cur;
    } else {
      ranges.push(start === prev ? `${start}` : (prev === start + 1 ? `${start},${prev}` : `${start}-${prev}`));
      start = cur;
      prev = cur;
    }
  }
  ranges.push(start === prev ? `${start}` : (prev === start + 1 ? `${start},${prev}` : `${start}-${prev}`));
  return ranges.join(",");
}

/**
 * IEEE format for multiple brackets: [1], [2] or [1]–[3]
 */
export function formatIeeeInText(nums) {
  if (!nums || nums.length === 0) return "";
  const unique = Array.from(new Set(nums.map(n => parseInt(n, 10)).filter(n => !isNaN(n)))).sort((a, b) => a - b);
  if (unique.length === 0) return "";

  const parts = [];
  let start = unique[0];
  let prev = start;

  for (let i = 1; i < unique.length; i++) {
    const cur = unique[i];
    if (cur === prev + 1) {
      prev = cur;
    } else {
      parts.push(start === prev ? `[${start}]` : (prev === start + 1 ? `[${start}], [${prev}]` : `[${start}]–[${prev}]`));
      start = cur;
      prev = cur;
    }
  }
  parts.push(start === prev ? `[${start}]` : (prev === start + 1 ? `[${start}], [${prev}]` : `[${start}]–[${prev}]`));
  return parts.join(", ");
}

/**
 * Format in-text Author-Date string for APA / Harvard / Chicago
 */
export function formatAuthorDateCitation(refsList, styleKey = "apa-7th") {
  if (!refsList || refsList.length === 0) return "";

  const citationStrings = refsList.map(ref => {
    const authors = parseAuthorNames(ref.authors);
    let authorStr = "Anonymous";
    if (authors.length === 1) {
      authorStr = authors[0].family;
    } else if (authors.length === 2) {
      authorStr = styleKey === "apa-7th"
        ? `${authors[0].family} & ${authors[1].family}`
        : `${authors[0].family} and ${authors[1].family}`;
    } else if (authors.length >= 3) {
      authorStr = `${authors[0].family} et al.`;
    }

    const yearStr = ref.year || (ref.raw_text.match(/\b(19\d\d|20\d\d)\b/) || ["n.d."])[0];
    return `${authorStr}, ${yearStr}`;
  });

  // Combine multiple references inside parentheses separated by semicolon
  return `(${citationStrings.join("; ")})`;
}

/**
 * Format in-text citation according to target style
 */
export function formatInTextForStyle(targetStyleKey, nums, refsList) {
  const style = CSL_STYLES[targetStyleKey] || CSL_STYLES["ama"];

  if (style.category === "author-date") {
    const text = formatAuthorDateCitation(refsList, targetStyleKey);
    return {
      text,
      isSuperscript: false,
      kind: "author-date"
    };
  }

  // Numeric styles
  if (targetStyleKey === "ieee") {
    return {
      text: formatIeeeInText(nums),
      isSuperscript: false,
      kind: "bracket"
    };
  }

  if (style.inTextKind === "bracket" || targetStyleKey === "vancouver-bracket") {
    const inner = condenseNumericRanges(nums);
    return {
      text: `[${inner}]`,
      isSuperscript: false,
      kind: "bracket"
    };
  }

  if (style.inTextKind === "paren" || targetStyleKey === "vancouver-paren") {
    const inner = condenseNumericRanges(nums);
    return {
      text: `(${inner})`,
      isSuperscript: false,
      kind: "paren"
    };
  }

  // Default: AMA / Nature (Superscript)
  return {
    text: condenseNumericRanges(nums),
    isSuperscript: true,
    kind: "sup"
  };
}

/**
 * Format a bibliography entry in AMA 11th edition style
 */
export function formatBibliographyEntryAma(num, ref) {
  const authors = parseAuthorNames(ref.authors);
  let authorStr = "";
  if (authors.length > 0) {
    if (authors.length <= 6) {
      authorStr = authors.map(a => `${a.family} ${a.given}`.trim()).join(", ");
    } else {
      authorStr = authors.slice(0, 3).map(a => `${a.family} ${a.given}`.trim()).join(", ") + ", et al";
    }
  }

  let titleStr = (ref.title || "").trim();
  if (titleStr && !titleStr.endsWith(".")) titleStr += ".";

  let journalStr = (ref.journal || "").trim();
  let pubStr = "";
  if (ref.year) pubStr += ref.year;
  if (ref.volume) {
    pubStr += `;${ref.volume}`;
    if (ref.issue) pubStr += `(${ref.issue})`;
  }
  if (ref.pages) pubStr += `:${ref.pages}`;
  if (pubStr && !pubStr.endsWith(".")) pubStr += ".";

  let doiStr = ref.doi ? `doi:${ref.doi}` : "";

  const segments = [
    authorStr,
    titleStr,
    journalStr ? (pubStr ? `${journalStr}. ${pubStr}` : journalStr) : pubStr,
    doiStr
  ].filter(Boolean);

  if (segments.length === 0) return `${num}. ${ref.raw_text}`;
  return `${num}. ${segments.join(" ")}`;
}

/**
 * Format a bibliography entry in Vancouver style
 */
export function formatBibliographyEntryVancouver(num, ref) {
  const authors = parseAuthorNames(ref.authors);
  let authorStr = "";
  if (authors.length > 0) {
    if (authors.length <= 6) {
      authorStr = authors.map(a => `${a.family} ${a.given}`.trim()).join(", ");
    } else {
      authorStr = authors.slice(0, 6).map(a => `${a.family} ${a.given}`.trim()).join(", ") + ", et al.";
    }
  }

  let titleStr = (ref.title || "").trim();
  if (titleStr && !titleStr.endsWith(".")) titleStr += ".";

  let journalStr = (ref.journal || "").trim();
  let pubStr = "";
  if (ref.year) pubStr += ref.year;
  if (ref.volume) {
    pubStr += `;${ref.volume}`;
    if (ref.issue) pubStr += `(${ref.issue})`;
  }
  if (ref.pages) pubStr += `:${ref.pages}`;
  if (pubStr && !pubStr.endsWith(".")) pubStr += ".";

  let doiStr = ref.doi ? `Available from: https://doi.org/${ref.doi}` : "";

  const segments = [
    authorStr,
    titleStr,
    journalStr ? (pubStr ? `${journalStr}. ${pubStr}` : journalStr) : pubStr,
    doiStr
  ].filter(Boolean);

  if (segments.length === 0) return `${num}. ${ref.raw_text}`;
  return `${num}. ${segments.join(" ")}`;
}

/**
 * Format a bibliography entry in APA 7th edition style
 */
export function formatBibliographyEntryApa7(ref) {
  const authors = parseAuthorNames(ref.authors);
  let authorStr = "";
  if (authors.length === 1) {
    authorStr = `${authors[0].family}, ${authors[0].given ? authors[0].given.charAt(0) + "." : ""}`;
  } else if (authors.length === 2) {
    const a1 = `${authors[0].family}, ${authors[0].given ? authors[0].given.charAt(0) + "." : ""}`;
    const a2 = `${authors[1].family}, ${authors[1].given ? authors[1].given.charAt(0) + "." : ""}`;
    authorStr = `${a1}, & ${a2}`;
  } else if (authors.length > 2) {
    const firstAuthors = authors.slice(0, 19).map(a => `${a.family}, ${a.given ? a.given.charAt(0) + "." : ""}`).join(", ");
    if (authors.length > 20) {
      const last = authors[authors.length - 1];
      authorStr = `${firstAuthors}, ... ${last.family}, ${last.given ? last.given.charAt(0) + "." : ""}`;
    } else {
      const last = authors[authors.length - 1];
      const prev = authors.slice(0, -1).map(a => `${a.family}, ${a.given ? a.given.charAt(0) + "." : ""}`).join(", ");
      authorStr = `${prev}, & ${last.family}, ${last.given ? last.given.charAt(0) + "." : ""}`;
    }
  }

  const yearStr = ref.year ? `(${ref.year}).` : "(n.d.).";
  let titleStr = (ref.title || "").trim();
  if (titleStr && !titleStr.endsWith(".")) titleStr += ".";

  let journalStr = (ref.journal || "").trim();
  let volumeStr = "";
  if (ref.volume) {
    volumeStr += ref.volume;
    if (ref.issue) volumeStr += `(${ref.issue})`;
  }
  if (ref.pages) {
    volumeStr += volumeStr ? `, ${ref.pages}.` : `${ref.pages}.`;
  } else if (volumeStr) {
    volumeStr += ".";
  }

  let doiStr = ref.doi ? `https://doi.org/${ref.doi}` : "";

  const segments = [
    authorStr,
    yearStr,
    titleStr,
    journalStr ? (volumeStr ? `${journalStr}, ${volumeStr}` : journalStr) : volumeStr,
    doiStr
  ].filter(Boolean);

  if (segments.length === 0) return ref.raw_text;
  return segments.join(" ");
}

/**
 * Format a bibliography entry in IEEE style
 */
export function formatBibliographyEntryIeee(num, ref) {
  const authors = parseAuthorNames(ref.authors);
  let authorStr = "";
  if (authors.length === 1) {
    authorStr = `${authors[0].given ? authors[0].given + " " : ""}${authors[0].family}`;
  } else if (authors.length === 2) {
    const a1 = `${authors[0].given ? authors[0].given + " " : ""}${authors[0].family}`;
    const a2 = `${authors[1].given ? authors[1].given + " " : ""}${authors[1].family}`;
    authorStr = `${a1} and ${a2}`;
  } else if (authors.length > 2) {
    const a1 = `${authors[0].given ? authors[0].given + " " : ""}${authors[0].family}`;
    authorStr = `${a1} et al.`;
  }

  let titleStr = (ref.title || "").trim();
  if (titleStr) titleStr = `"${titleStr},"`;

  let journalStr = (ref.journal || "").trim();
  let details = [];
  if (journalStr) details.push(journalStr);
  if (ref.volume) details.push(`vol. ${ref.volume}`);
  if (ref.issue) details.push(`no. ${ref.issue}`);
  if (ref.pages) details.push(`pp. ${ref.pages}`);
  if (ref.year) details.push(`${ref.year}`);

  let detailsStr = details.join(", ");
  if (detailsStr && !detailsStr.endsWith(".")) detailsStr += ".";

  let doiStr = ref.doi ? `doi: ${ref.doi}.` : "";

  const segments = [
    authorStr ? `${authorStr},` : "",
    titleStr,
    detailsStr,
    doiStr
  ].filter(Boolean);

  if (segments.length === 0) return `[${num}] ${ref.raw_text}`;
  return `[${num}] ${segments.join(" ")}`;
}

/**
 * Format a bibliography entry in Nature style
 */
export function formatBibliographyEntryNature(num, ref) {
  const authors = parseAuthorNames(ref.authors);
  let authorStr = "";
  if (authors.length === 1) {
    authorStr = `${authors[0].family}, ${authors[0].given || ""}`.trim();
  } else if (authors.length === 2) {
    authorStr = `${authors[0].family}, ${authors[0].given || ""}`.trim() + " & " + `${authors[1].family}, ${authors[1].given || ""}`.trim();
  } else if (authors.length > 2) {
    authorStr = `${authors[0].family}, ${authors[0].given || ""}`.trim() + " et al.";
  }

  let titleStr = (ref.title || "").trim();
  if (titleStr && !titleStr.endsWith(".")) titleStr += ".";

  let journalStr = (ref.journal || "").trim();
  let pubStr = "";
  if (ref.volume) pubStr += ref.volume;
  if (ref.pages) pubStr += pubStr ? `, ${ref.pages}` : ref.pages;
  if (ref.year) pubStr += pubStr ? ` (${ref.year}).` : `(${ref.year}).`;

  const segments = [
    authorStr,
    titleStr,
    journalStr ? (pubStr ? `${journalStr} ${pubStr}` : journalStr) : pubStr
  ].filter(Boolean);

  if (segments.length === 0) return `${num}. ${ref.raw_text}`;
  return `${num}. ${segments.join(" ")}`;
}

/**
 * Dispatcher to format any bibliography entry in the chosen target style
 */
export function formatBibliographyForStyle(targetStyleKey, num, ref) {
  switch (targetStyleKey) {
    case "apa-7th":
    case "harvard":
      return formatBibliographyEntryApa7(ref);
    case "vancouver-bracket":
    case "vancouver-paren":
    case "european-radiology":
    case "cvir":
    case "pediatric-radiology":
      return formatBibliographyEntryVancouver(num, ref);
    case "ieee":
      return formatBibliographyEntryIeee(num, ref);
    case "nature":
      return formatBibliographyEntryNature(num, ref);
    case "radiology":
    case "ajnr":
    case "ajr":
    case "radiographics":
    case "jvir":
    case "jacr":
    case "investigative-radiology":
    case "academic-radiology":
    case "clinical-radiology":
    case "korean-journal-of-radiology":
    case "journal-of-nuclear-medicine":
    case "ama":
    default:
      return formatBibliographyEntryAma(num, ref);
  }
}

/**
 * Sort bibliography references according to the target style specification:
 * - Numeric styles (AMA, Vancouver, IEEE, Nature): sorted by order of appearance in body text
 * - Author-Date styles (APA 7th, Harvard): sorted alphabetically by primary author's family name, then year, then title
 */
export function sortReferencesForStyle(targetStyleKey, references, citationOrderMap) {
  const style = CSL_STYLES[targetStyleKey] || CSL_STYLES["ama"];

  if (style.sort === "alphabetical") {
    // APA / Harvard: Alphabetical by first author surname, then year, then title
    return [...references].sort((a, b) => {
      const aAuth = (parseAuthorNames(a.authors)[0]?.family || a.raw_text).toLowerCase();
      const bAuth = (parseAuthorNames(b.authors)[0]?.family || b.raw_text).toLowerCase();
      if (aAuth !== bAuth) return aAuth.localeCompare(bAuth);

      const aYear = parseInt(a.year || "0", 10);
      const bYear = parseInt(b.year || "0", 10);
      if (aYear !== bYear) return aYear - bYear;

      return (a.title || "").localeCompare(b.title || "");
    });
  }

  // Numeric styles: Sequential order of appearance
  return [...references].sort((a, b) => {
    const aOrder = citationOrderMap[a.ref_num] !== undefined ? citationOrderMap[a.ref_num] : 999999;
    const bOrder = citationOrderMap[b.ref_num] !== undefined ? citationOrderMap[b.ref_num] : 999999;
    if (aOrder !== bOrder) return aOrder - bOrder;
    return a.ref_num - b.ref_num;
  });
}
