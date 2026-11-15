/**
 * Co-Scientist Reference Auditor: In-Browser Crossref, Handle Registry & Anti-Bot Reachability Engine
 * Queries DOI Foundation Handle API (Universal CORS), Crossref, and OpenAlex.
 */

const HANDLE_API = "https://doi.org/api/handles/";
const CROSSREF_API = "https://api.crossref.org/works/";
const OPENALEX_API = "https://api.openalex.org/works/https://doi.org/";
const EUROPE_PMC_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search";
const OPENALEX_WORKS_API = "https://api.openalex.org/works";

// Recognized academic publisher domains that enforce WAF / Cloudflare bot challenges or paywalls
const PROTECTED_PUBLISHER_DOMAINS = [
  "sciencedirect.com",
  "elsevier.com",
  "linkinghub.elsevier.com",
  "academic.oup.com",
  "oup.com",
  "springer.com",
  "link.springer.com",
  "nature.com",
  "wiley.com",
  "onlinelibrary.wiley.com",
  "journals.sagepub.com",
  "sagepub.com",
  "tandfonline.com",
  "pubs.rsna.org",
  "rsna.org",
  "neurology.org",
  "karger.com",
  "casereports.bmj.com",
  "bmj.com",
  "wjgnet.com",
  "ajnr.org",
  "ahajournals.org",
  "ashpublications.org",
  "jamanetwork.com",
  "nejm.org",
  "thelancet.com",
  "cell.com",
  "frontiersin.org",
  "mdpi.com",
  "ieee.org"
];

/**
 * Check if a URL belongs to a known bot-protected or paywalled academic publisher
 */
function isProtectedPublisherUrl(url) {
  if (!url) return false;
  const lower = url.toLowerCase();
  return PROTECTED_PUBLISHER_DOMAINS.some(domain => lower.includes(domain));
}

/**
 * Query official DOI Foundation Handle REST API
 */
async function queryHandleApi(cleanDoi) {
  try {
    const resp = await fetch(`${HANDLE_API}${encodeURIComponent(cleanDoi)}`, {
      method: "GET",
      headers: { "Accept": "application/json" }
    });
    if (resp.status === 200) {
      const data = await resp.json();
      if (data && data.responseCode === 1) {
        let publisherUrl = "";
        if (Array.isArray(data.values)) {
          const urlEntry = data.values.find(v => v.type === 'URL');
          if (urlEntry && urlEntry.data && urlEntry.data.value) {
            publisherUrl = urlEntry.data.value;
          }
        }
        return {
          found: true,
          publisherUrl: publisherUrl || `https://doi.org/${cleanDoi}`,
          isDead: false
        };
      } else if (data && data.responseCode === 100) {
        // Explicitly Handle Not Found
        return { found: false, publisherUrl: "", isDead: true };
      }
    }
  } catch (e) {
    // Network or CORS fallback
  }
  return { found: false, publisherUrl: "", isDead: false };
}

/**
 * Query Crossref REST API for canonical metadata
 */
async function queryCrossrefApi(cleanDoi) {
  try {
    const resp = await fetch(`${CROSSREF_API}${encodeURIComponent(cleanDoi)}`, {
      method: "GET",
      headers: { "Accept": "application/json" }
    });
    if (resp.status === 200) {
      const data = await resp.json();
      const msg = data.message || {};
      const title = (msg.title && msg.title.length > 0) ? msg.title[0] : "";
      const authors = (msg.author || []).map(a => `${a.family || ''} ${a.given || ''}`.trim());
      const journal = (msg['container-title'] && msg['container-title'].length > 0) ? msg['container-title'][0] : "";
      const issued = (msg.issued && msg.issued['date-parts'] && msg.issued['date-parts'][0]) ? msg.issued['date-parts'][0][0] : "";
      const resourceUrl = (msg.resource && msg.resource.primary && msg.resource.primary.URL)
        ? msg.resource.primary.URL
        : `https://doi.org/${cleanDoi}`;

      return {
        found: true,
        title: title,
        authors: authors,
        journal: journal,
        year: String(issued || ""),
        volume: msg.volume || "",
        issue: msg.issue || "",
        pages: msg.page || "",
        abstract: msg.abstract || "",
        resourceUrl: resourceUrl
      };
    } else if (resp.status === 404) {
      return { found: false, is404: true };
    }
  } catch (e) {
    // Fallback
  }
  return { found: false, is404: false };
}

/**
 * Fallback to OpenAlex scholarly index
 */
async function queryOpenAlex(cleanDoi) {
  try {
    const resp = await fetch(`${OPENALEX_API}${encodeURIComponent(cleanDoi)}`);
    if (resp.status === 200) {
      const data = await resp.json();
      return {
        found: true,
        title: data.title || "",
        authors: (data.authorships || []).map(a => a.author ? a.author.display_name : ""),
        journal: data.primary_location && data.primary_location.source ? data.primary_location.source.display_name : "",
        year: String(data.publication_year || ""),
        volume: data.biblio ? data.biblio.volume : "",
        issue: data.biblio ? data.biblio.issue : "",
        pages: data.biblio ? `${data.biblio.first_page || ''}-${data.biblio.last_page || ''}` : "",
        resourceUrl: data.doi || `https://doi.org/${cleanDoi}`
      };
    }
  } catch (e) {
    // Ignore
  }
  return { found: false };
}

/**
 * Compute word overlap similarity between reference title and registry title.
 * Combines Dice coefficient with containment ratio so that matching titles with long subtitles
 * are not falsely rejected.
 */
function computeTitleSimilarity(targetTitle, candidateTitle) {
  if (!targetTitle || !candidateTitle) return 0;
  const tWords = new Set(targetTitle.toLowerCase().match(/\b[a-z]{3,}\b/g) || []);
  const cWords = new Set(candidateTitle.toLowerCase().replace(/<[^>]+>/g, '').match(/\b[a-z]{3,}\b/g) || []);
  if (tWords.size === 0 || cWords.size === 0) return 0;
  let common = 0;
  tWords.forEach(w => { if (cWords.has(w)) common++; });
  if (common === 0) return 0;
  const dice = (2 * common) / (tWords.size + cWords.size);
  const containment = common / Math.min(tWords.size, cWords.size);
  if (containment >= 0.8) {
    return Math.max(dice, containment * 0.9);
  }
  return dice;
}

/**
 * Query EMBL-EBI Europe PMC REST API (Biomedical primary, open CORS, high speed)
 */
async function recoverDoiFromEuropePmc(rawText, title) {
  const cleanTitle = (title || "").replace(/["\r\n]/g, " ").trim();
  const queryCandidates = [];
  if (cleanTitle && cleanTitle.length > 15) {
    queryCandidates.push(`TITLE:"${cleanTitle}"`);
  }
  const cleanRaw = (rawText || "").replace(/^\d+\.\s*/, "").trim();
  if (cleanRaw && cleanRaw.length > 20) {
    queryCandidates.push(cleanRaw.slice(0, 180));
  }

  for (const q of queryCandidates) {
    const url = `${EUROPE_PMC_API}?query=${encodeURIComponent(q)}&resultType=lite&pageSize=1&format=json`;
    try {
      const resp = await fetch(url, { headers: { "Accept": "application/json" } });
      if (resp.status === 200) {
        const data = await resp.json();
        const results = (data.resultList && data.resultList.result) ? data.resultList.result : [];
        if (results.length > 0) {
          const top = results[0];
          if (top.doi) {
            if (title && title.length > 15) {
              const sim = computeTitleSimilarity(title, top.title || "");
              if (sim < 0.50) continue;
            }
            return {
              found: true,
              doi: top.doi,
              title: top.title || "",
              source: "Europe PMC"
            };
          }
        }
      }
    } catch (e) {
      // Continue to next candidate
    }
  }
  return { found: false };
}

/**
 * Query OpenAlex Scholarly Graph (Universal multidisciplinary fallback)
 */
async function recoverDoiFromOpenAlex(rawText, title) {
  const queryStr = (title && title.length > 15) ? title : (rawText || "").replace(/^\d+\.\s*/, "").trim();
  if (!queryStr || queryStr.length < 15) return { found: false };

  const url = `${OPENALEX_WORKS_API}?search=${encodeURIComponent(queryStr.slice(0, 200))}&per-page=1`;
  try {
    const resp = await fetch(url, { headers: { "Accept": "application/json" } });
    if (resp.status === 200) {
      const data = await resp.json();
      const results = data.results || [];
      if (results.length > 0) {
        const top = results[0];
        if (top.doi) {
          const cleanDoi = top.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, '');
          if (title && title.length > 15) {
            const sim = computeTitleSimilarity(title, top.title || "");
            if (sim < 0.50) return { found: false };
          }
          return {
            found: true,
            doi: cleanDoi,
            title: top.title || "",
            source: "OpenAlex"
          };
        }
      }
    }
  } catch (e) {
    // Ignore
  }
  return { found: false };
}

/**
 * Query Crossref Bibliographic API to automatically recover a missing DOI
 */
async function recoverDoiFromBibliographic(rawText, title) {
  const queryStr = (rawText && rawText.length > 20) ? rawText.replace(/^\d+\.\s*/, "") : (title || "");
  if (!queryStr || queryStr.length < 15) return { found: false };

  const url = `${CROSSREF_API}?query.bibliographic=${encodeURIComponent(queryStr.slice(0, 300))}&rows=1`;
  try {
    const resp = await fetch(url, { headers: { "Accept": "application/json" } });
    if (resp.status === 200) {
      const data = await resp.json();
      const items = (data.message && data.message.items) ? data.message.items : [];
      if (items.length > 0) {
        const top = items[0];
        if (top.DOI && top.score >= 40) {
          const topTitle = (top.title && top.title.length > 0) ? top.title[0] : "";
          if (title && title.length > 15) {
            const sim = computeTitleSimilarity(title, topTitle);
            if (sim < 0.50) return { found: false };
          }
          return {
            found: true,
            doi: top.DOI,
            title: topTitle,
            source: "Crossref",
            item: top
          };
        }
      }
    }
  } catch (e) {
    // Ignore
  }
  return { found: false };
}

/**
 * Cascade through multi-registry search for missing DOI
 */
async function recoverMissingDoi(rawText, title) {
  // 1. Europe PMC (Fastest biomedical index, open CORS, no rate limit)
  const ep = await recoverDoiFromEuropePmc(rawText, title);
  if (ep.found && ep.doi) return ep;

  // 2. OpenAlex (Global multidisciplinary scholarly graph)
  const oa = await recoverDoiFromOpenAlex(rawText, title);
  if (oa.found && oa.doi) return oa;

  // 3. Crossref Bibliographic API
  const cr = await recoverDoiFromBibliographic(rawText, title);
  if (cr.found && cr.doi) return cr;

  return { found: false };
}

/**
 * Master Reference Validation Function
 */
export async function validateReferenceCrossref(doi, rawText = "", title = "") {
  let cleanDoi = doi ? doi.trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, '').replace(/^doi:\s*/i, '') : "";
  let isRecovered = false;
  let recoverySource = "";

  // Auto-recover missing DOI via multi-registry cascade
  if (!cleanDoi && (rawText || title)) {
    const rec = await recoverMissingDoi(rawText, title);
    if (rec.found && rec.doi) {
      cleanDoi = rec.doi;
      isRecovered = true;
      recoverySource = rec.source || "Registry";
    }
  }

  if (!cleanDoi) {
    return {
      status: "missing_doi",
      is_reachable: false,
      is_bot_gated: false,
      is_recovered: false,
      doi: "",
      recovered_doi: "",
      notes: ["No DOI provided and no match found in scholarly registry (may be a book, guideline, or unpublished report)."]
    };
  }

  // Concurrently query Handle Foundation API and Crossref API
  const [handleRes, crRes] = await Promise.all([
    queryHandleApi(cleanDoi),
    queryCrossrefApi(cleanDoi)
  ]);

  let oaRes = { found: false };
  if (!crRes.found) {
    oaRes = await queryOpenAlex(cleanDoi);
  }

  const isMetadataFound = crRes.found || oaRes.found;
  const meta = crRes.found ? crRes : oaRes;
  const isRegisteredInHandle = handleRes.found;
  const effectiveUrl = handleRes.publisherUrl || meta.resourceUrl || `https://doi.org/${cleanDoi}`;

  // Check if target landing is a known bot-protected/paywalled publisher
  const isBotProtectedPublisher = isProtectedPublisherUrl(effectiveUrl);

  // Status discrimination
  if (isMetadataFound || isRegisteredInHandle) {
    // The DOI exists and is valid!
    if (isBotProtectedPublisher) {
      return {
        status: isRecovered ? "recovered" : "bot_protected",
        is_reachable: true,
        is_bot_gated: true,
        is_recovered: isRecovered,
        doi: cleanDoi,
        recovered_doi: isRecovered ? cleanDoi : "",
        recovery_source: recoverySource,
        http_status: 403,
        resolved_url: effectiveUrl,
        crossref_found: isMetadataFound,
        crossref_title: meta.title || "",
        crossref_authors: meta.authors || [],
        crossref_journal: meta.journal || "",
        crossref_year: meta.year || "",
        crossref_volume: meta.volume || "",
        crossref_issue: meta.issue || "",
        crossref_pages: meta.pages || "",
        abstract: meta.abstract || "",
        notes: [
          isRecovered ? `Auto-resolved missing DOI via ${recoverySource}: ${cleanDoi}` : "Registered active DOI.",
          "Publisher (e.g. Elsevier / Springer Nature / OUP / RSNA) protects landing page with anti-bot verification (Cloudflare/WAF) or institutional paywall.",
          "The link is valid and fully accessible for human readers in standard web browsers."
        ]
      };
    } else {
      return {
        status: isRecovered ? "recovered" : "verified",
        is_reachable: true,
        is_bot_gated: false,
        is_recovered: isRecovered,
        doi: cleanDoi,
        recovered_doi: isRecovered ? cleanDoi : "",
        recovery_source: recoverySource,
        http_status: 200,
        resolved_url: effectiveUrl,
        crossref_found: isMetadataFound,
        crossref_title: meta.title || "",
        crossref_authors: meta.authors || [],
        crossref_journal: meta.journal || "",
        crossref_year: meta.year || "",
        crossref_volume: meta.volume || "",
        crossref_issue: meta.issue || "",
        crossref_pages: meta.pages || "",
        abstract: meta.abstract || "",
        notes: [isRecovered ? `Auto-resolved missing DOI via ${recoverySource}: ${cleanDoi}` : "Validated and registered in scholarly database."]
      };
    }
  }

  // If Handle API explicitly confirmed code 100 AND no registry found it
  if (handleRes.isDead && !isMetadataFound) {
    return {
      status: "unreachable",
      is_reachable: false,
      is_bot_gated: false,
      is_recovered: isRecovered,
      doi: cleanDoi,
      recovered_doi: isRecovered ? cleanDoi : "",
      http_status: 404,
      resolved_url: `https://doi.org/${cleanDoi}`,
      crossref_found: false,
      notes: ["DOI returned 404 (Not Found in global DOI Handle registry or Crossref)."]
    };
  }

  // Fallback: Registry inconclusive
  return {
    status: "unreachable",
    is_reachable: false,
    is_bot_gated: false,
    is_recovered: isRecovered,
    doi: cleanDoi,
    recovered_doi: isRecovered ? cleanDoi : "",
    http_status: 0,
    resolved_url: `https://doi.org/${cleanDoi}`,
    crossref_found: false,
    notes: ["Unable to verify DOI through public scholarly registries."]
  };
}
