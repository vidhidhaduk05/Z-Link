/**
 * Co-Scientist Reference Auditor: In-Browser Crossref & Reachability Engine
 * Executes direct CORS requests to Crossref and PubMed APIs.
 */

const CROSSREF_API = "https://api.crossref.org/works/";
const PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi";
const PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi";

export async function validateReferenceCrossref(doi) {
  if (!doi) {
    return {
      status: "missing_doi",
      is_reachable: false,
      notes: ["No DOI provided in reference entry."]
    };
  }

  const cleanDoi = doi.trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, '').replace(/^doi:\s*/i, '');
  const url = `${CROSSREF_API}${encodeURIComponent(cleanDoi)}`;

  try {
    const resp = await fetch(url, {
      method: "GET",
      headers: {
        "Accept": "application/json"
      }
    });

    if (resp.status === 200) {
      const data = await resp.json();
      const msg = data.message || {};
      
      const title = (msg.title && msg.title.length > 0) ? msg.title[0] : "";
      const authors = (msg.author || []).map(a => `${a.family || ''} ${a.given || ''}`.trim());
      const journal = (msg['container-title'] && msg['container-title'].length > 0) ? msg['container-title'][0] : "";
      const issued = (msg.issued && msg.issued['date-parts'] && msg.issued['date-parts'][0]) ? msg.issued['date-parts'][0][0] : "";
      const volume = msg.volume || "";
      const issue = msg.issue || "";
      const pages = msg.page || "";
      const abstract = msg.abstract || "";
      const resourceUrl = (msg.resource && msg.resource.primary && msg.resource.primary.URL) ? msg.resource.primary.URL : `https://doi.org/${cleanDoi}`;

      return {
        status: "verified",
        is_reachable: true,
        http_status: 200,
        resolved_url: resourceUrl,
        crossref_found: true,
        crossref_title: title,
        crossref_authors: authors,
        crossref_journal: journal,
        crossref_year: String(issued),
        crossref_volume: volume,
        crossref_issue: issue,
        crossref_pages: pages,
        abstract: abstract,
        notes: ["Validated and registered in Crossref database."]
      };
    } else if (resp.status === 404) {
      return {
        status: "unreachable",
        is_reachable: false,
        http_status: 404,
        resolved_url: `https://doi.org/${cleanDoi}`,
        crossref_found: false,
        notes: ["DOI returned 404 (Not Found in Crossref)."]
      };
    } else {
      return {
        status: "unreachable",
        is_reachable: false,
        http_status: resp.status,
        resolved_url: `https://doi.org/${cleanDoi}`,
        crossref_found: false,
        notes: [`Crossref responded with HTTP status ${resp.status}`]
      };
    }
  } catch (err) {
    // If network or CORS blocked direct doi.org, try openalex fallback
    return await queryOpenAlexFallback(cleanDoi);
  }
}

async function queryOpenAlexFallback(cleanDoi) {
  try {
    const oaUrl = `https://api.openalex.org/works/https://doi.org/${encodeURIComponent(cleanDoi)}`;
    const resp = await fetch(oaUrl);
    if (resp.status === 200) {
      const data = await resp.json();
      return {
        status: "verified",
        is_reachable: true,
        http_status: 200,
        resolved_url: data.doi || `https://doi.org/${cleanDoi}`,
        crossref_found: true,
        crossref_title: data.title || "",
        crossref_authors: (data.authorships || []).map(a => a.author ? a.author.display_name : ""),
        crossref_journal: data.primary_location && data.primary_location.source ? data.primary_location.source.display_name : "",
        crossref_year: String(data.publication_year || ""),
        crossref_volume: data.biblio ? data.biblio.volume : "",
        crossref_issue: data.biblio ? data.biblio.issue : "",
        crossref_pages: data.biblio ? `${data.biblio.first_page || ''}-${data.biblio.last_page || ''}` : "",
        notes: ["Verified through OpenAlex scholarly index."]
      };
    }
  } catch (e) {
    // ignore
  }

  return {
    status: "unreachable",
    is_reachable: false,
    http_status: 0,
    resolved_url: `https://doi.org/${cleanDoi}`,
    crossref_found: false,
    notes: ["Unable to verify DOI through public scholarly registries."]
  };
}

