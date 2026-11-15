/**
 * Co-Scientist Reference Auditor & Zotero Linker: Main UI Controller
 * Implements Ponytail Guarded State Machine and Master Theme interactions.
 */

import { parseDocxFile, injectZoteroFieldsInBrowser } from './docx_engine.js';
import { validateReferenceCrossref } from './crossref_audit.js';
import { generateClientRis } from './ris_generator.js';

let appState = {
  fsmState: 'IDLE',
  currentFile: null,
  fileName: '',
  parsedData: null,
  verdicts: {},
  mappings: {},
  selectedRefNum: 1,
  backendUrl: '' // optional
};
window.appState = appState;

// DOM Elements
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const btnSample = document.getElementById('btnSample');
const btnActa2 = document.getElementById('btnActa2');
const citationFormatSelect = document.getElementById('citationFormatSelect');
const customFormatInput = document.getElementById('customFormatInput');
const resultsSection = document.getElementById('resultsSection');
const tableBody = document.getElementById('referencesTableBody');
const manuscriptViewer = document.getElementById('manuscriptViewer');
const activeRefCard = document.getElementById('activeRefCard');

// Metrics
const metricCitations = document.getElementById('metricCitations');
const metricReferences = document.getElementById('metricReferences');
const metricReachable = document.getElementById('metricReachable');
const metricBotGated = document.getElementById('metricBotGated');
const metricBroken = document.getElementById('metricBroken');
const metricSequence = document.getElementById('metricSequence');

// Stepper items
const steps = {
  upload: document.getElementById('step-upload'),
  parse: document.getElementById('step-parse'),
  audit: document.getElementById('step-audit'),
  mapping: document.getElementById('step-mapping'),
  ready: document.getElementById('step-ready')
};

// Deliverable buttons
const btnDownloadTrackedDocx = document.getElementById('btnDownloadTrackedDocx');
const btnDownloadDocx = document.getElementById('btnDownloadDocx');
const btnDownloadRis = document.getElementById('btnDownloadRis');
const btnDownloadReport = document.getElementById('btnDownloadReport');

function setStepper(activeKey) {
  const keys = ['upload', 'parse', 'audit', 'mapping', 'ready'];
  const activeIdx = keys.indexOf(activeKey);
  keys.forEach((k, idx) => {
    const el = steps[k];
    if (!el) return;
    el.classList.remove('active', 'done');
    if (idx < activeIdx) el.classList.add('done');
    else if (idx === activeIdx) el.classList.add('active');
  });
}

// ---------------- Drag & Drop Ingest ----------------

// Global window guards: prevent browser from opening/downloading dropped file if dropped outside dropzone
window.addEventListener('dragover', (e) => {
  e.preventDefault();
}, false);

window.addEventListener('drop', (e) => {
  e.preventDefault();
}, false);

if (dropzone && fileInput) {
  dropzone.addEventListener('click', () => fileInput.click());

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
      }
      dropzone.classList.add('dragover');
    });
  });

  dropzone.addEventListener('dragleave', (e) => {
    e.preventDefault();
    e.stopPropagation();
    // Only remove class if leaving the dropzone element itself
    if (e.currentTarget === dropzone && (!e.relatedTarget || !dropzone.contains(e.relatedTarget))) {
      dropzone.classList.remove('dragover');
    }
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.remove('dragover');
    const dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length > 0) {
      handleFileSelected(dt.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      fileInput.value = ''; // Reset so the same file can be re-selected if needed
      handleFileSelected(file);
    }
  });
}

if (btnSample) {
  btnSample.addEventListener('click', async () => {
    try {
      btnSample.textContent = '⏳ Loading Sample...';
      const resp = await fetch('sample_radiology_manuscript.docx');
      if (!resp.ok) throw new Error("Could not find sample manuscript file.");
      const blob = await resp.blob();
      const file = new File([blob], "sample_radiology_manuscript.docx", {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      });
      await handleFileSelected(file);
      btnSample.textContent = '📄 Sample Radiology Paper';
    } catch (err) {
      alert("Error loading sample: " + err.message);
      btnSample.textContent = '📄 Sample Radiology Paper';
    }
  });
}

if (btnActa2) {
  btnActa2.addEventListener('click', async () => {
    try {
      btnActa2.textContent = '⏳ Loading ACTA2 Manuscript...';
      const resp = await fetch('ACTA2_Manuscript_11.14.2026.docx');
      if (!resp.ok) throw new Error("Could not find ACTA2 manuscript file.");
      const blob = await resp.blob();
      const file = new File([blob], "ACTA2_Manuscript_11.14.2026.docx", {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      });
      if (citationFormatSelect) citationFormatSelect.value = 'sup';
      await handleFileSelected(file);
      btnActa2.textContent = '📋 Load ACTA2 Manuscript (43 Refs)';
    } catch (err) {
      alert("Error loading ACTA2 manuscript: " + err.message);
      btnActa2.textContent = '📋 Load ACTA2 Manuscript (43 Refs)';
    }
  });
}

if (citationFormatSelect && customFormatInput) {
  citationFormatSelect.addEventListener('change', () => {
    if (citationFormatSelect.value === 'custom') {
      customFormatInput.style.display = 'inline-block';
      customFormatInput.focus();
    } else {
      customFormatInput.style.display = 'none';
    }
  });
}

// ---------------- Pipeline Execution ----------------

async function handleFileSelected(file) {
  if (!file.name.toLowerCase().endsWith('.docx')) {
    alert("Please upload a Microsoft Word document (.docx).");
    return;
  }

  const selectedFormat = citationFormatSelect ? citationFormatSelect.value : 'auto';

  appState.currentFile = file;
  appState.fileName = file.name;
  appState.fsmState = 'PARSING';
  setStepper('parse');

  resultsSection.style.display = 'block';
  resultsSection.scrollIntoView({ behavior: 'smooth' });

  // 1. In-Browser Parse
  try {
    const parsed = await parseDocxFile(file, selectedFormat);
    appState.parsedData = parsed;
  } catch (err) {
    alert("Failed to parse Word document: " + err.message);
    setStepper('upload');
    return;
  }

  // 2. Validate and check reachability
  appState.fsmState = 'VALIDATING';
  setStepper('audit');

  metricCitations.textContent = appState.parsedData.sites.length;
  metricReferences.textContent = appState.parsedData.references.length;

  // Display active format profile
  const formatNames = {
    sup: "Superscript (AMA / Nature)",
    bracket: "Square Brackets [1, 2]",
    paren: "Parentheses (1, 2)",
    mixed: "Mixed (Superscripts & Parens)",
    punct_sup: "Punctuation Superscript"
  };
  const fmtKey = appState.parsedData.detectedFormat || selectedFormat;
  const fmtDisplay = formatNames[fmtKey] || fmtKey || "Auto-Profiled";
  const citSub = document.querySelector("#metricCitations + .metric-sub") || document.querySelectorAll(".metric-card .metric-sub")[0];
  if (citSub) {
    citSub.innerHTML = `Format: <strong>${fmtDisplay}</strong> (Prose Protected)`;
  }

  appState.verdicts = {};
  let reachableCount = 0;
  let botGatedCount = 0;
  let brokenCount = 0;

  // Initial sentence & usage mapping and instant audit table display so the user sees the audit immediately!
  computeUsageMappings();
  renderAuditTable();
  renderManuscriptExplorer();
  updateActiveReferenceCard(1);

  // Process references through a concurrency-controlled queue to respect registry rate limits
  const CONCURRENCY_LIMIT = 3;
  const refsQueue = [...appState.parsedData.references];

  async function validationWorker() {
    while (refsQueue.length > 0) {
      const ref = refsQueue.shift();
      if (!ref) break;
      const verdict = await validateReferenceCrossref(ref.doi, ref.raw_text, ref.title);
      appState.verdicts[ref.ref_num] = verdict;
      if (verdict.is_recovered && verdict.recovered_doi) {
        ref.doi = verdict.recovered_doi;
      }
      if (verdict.status === 'verified' || verdict.status === 'recovered') reachableCount++;
      else if (verdict.status === 'bot_protected' || verdict.is_bot_gated) botGatedCount++;
      else if (verdict.status === 'unreachable') brokenCount++;

      metricReachable.textContent = reachableCount;
      if (metricBotGated) metricBotGated.textContent = botGatedCount;
      metricBroken.textContent = brokenCount;

      // Update the specific row dynamically in real time
      updateAuditTableRow(ref.ref_num);

      // Polite 80ms interval
      await new Promise(r => setTimeout(r, 80));
    }
  }

  const workers = Array.from({ length: Math.min(CONCURRENCY_LIMIT, refsQueue.length) }, () => validationWorker());
  await Promise.all(workers);

  // 3. Re-compute sentence & usage mappings and finalize display
  appState.fsmState = 'MAPPING';
  setStepper('mapping');
  computeUsageMappings();

  // 4. Final UI Refresh
  renderAuditTable();
  updateActiveReferenceCard(1);

  // 5. Ready for Linking & Download
  appState.fsmState = 'READY';
  setStepper('ready');
}

function computeUsageMappings() {
  const { references, sites, paraTexts } = appState.parsedData;
  const mappings = {};
  const firstSeenOrder = [];
  const warnings = [];

  references.forEach(r => {
    mappings[r.ref_num] = {
      occurrences: [],
      firstMentionPara: -1,
      firstMentionSentence: "Not cited in body text."
    };
  });

  sites.forEach(s => {
    s.nums.forEach(num => {
      if (mappings[num]) {
        mappings[num].occurrences.push({
          paragraphIdx: s.paragraph_idx,
          citationText: s.text,
          sentence: s.sentence
        });
      }
      if (!firstSeenOrder.includes(num)) {
        firstSeenOrder.push(num);
      }
    });
  });

  let seqValid = true;
  let expectedNext = 1;
  firstSeenOrder.forEach(seen => {
    if (seen > expectedNext) {
      seqValid = false;
      warnings.push(`Reference [${seen}] cited before Reference [${expectedNext}].`);
      expectedNext = Math.max(expectedNext, seen + 1);
    } else if (seen === expectedNext) {
      expectedNext++;
    }
  });

  // Calculate AMA Sequential 1..N mapping
  const amaMapping = {};
  firstSeenOrder.forEach((oldNum, idx) => {
    amaMapping[oldNum] = idx + 1;
  });
  let nextUncited = firstSeenOrder.length + 1;
  references.forEach(r => {
    if (!firstSeenOrder.includes(r.ref_num)) {
      amaMapping[r.ref_num] = nextUncited++;
    }
  });

  const hasOrderChanges = Object.keys(amaMapping).some(k => parseInt(k, 10) !== amaMapping[k]);
  appState.amaMapping = amaMapping;
  appState.firstSeenOrder = firstSeenOrder;
  appState.hasOrderChanges = hasOrderChanges;

  if (hasOrderChanges) {
    metricSequence.innerHTML = `<span style="color: #b45309;" title="Auto-Renumbering Active: Citations will be re-ordered consecutively 1..N in Word and RIS">Auto-Reordering to AMA 1..N</span>`;
  } else {
    metricSequence.textContent = "Consecutive (Valid 1..N)";
    metricSequence.style.color = "var(--status-reachable)";
  }

  references.forEach(r => {
    const m = mappings[r.ref_num];
    if (m.occurrences.length > 0) {
      m.firstMentionPara = m.occurrences[0].paragraphIdx;
      m.firstMentionSentence = m.occurrences[0].sentence;
    }
  });

  appState.mappings = mappings;
}

// ---------------- UI Renderers ----------------

function renderAuditTable() {
  tableBody.innerHTML = '';
  const { references } = appState.parsedData;

  references.forEach(ref => {
    const v = appState.verdicts[ref.ref_num] || {};
    const m = (appState.mappings && appState.mappings[ref.ref_num]) || { occurrences: [] };

    const tr = document.createElement('tr');
    tr.id = 'ref-row-' + ref.ref_num;
    tr.dataset.refNum = ref.ref_num;
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', () => {
      updateActiveReferenceCard(ref.ref_num);
      highlightSentenceInManuscript(ref.ref_num);
    });

    let badgeClass = 'missing';
    let badgeText = 'No DOI';
    let actionBtnHtml = '';
    let autoRecoveredPill = '';

    if (v.status === 'recovered' || v.is_recovered) {
      badgeClass = 'recovered';
      badgeText = '🔍 DOI Recovered';
      const regSource = v.recovery_source || "Registry";
      autoRecoveredPill = `<span class="badge-auto-recovered" title="Automatically matched and verified via ${regSource}">Auto-Found (${regSource})</span>`;
      if (ref.doi) {
        actionBtnHtml = `<a href="https://doi.org/${encodeURIComponent(ref.doi)}" target="_blank" class="btn-open-ext" title="Verify auto-recovered DOI landing">Verify ↗</a>`;
      }
    } else if (v.status === 'bot_protected' || v.is_bot_gated) {
      badgeClass = 'bot-protected';
      badgeText = '🛡️ Bot Check / Paywall';
      if (ref.doi) {
        actionBtnHtml = `<a href="https://doi.org/${encodeURIComponent(ref.doi)}" target="_blank" class="btn-open-ext" title="Open directly in browser to view article or solve publisher verification">Verify ↗</a>`;
      }
    } else if (v.status === 'verified' || (v.is_reachable && !v.is_bot_gated)) {
      badgeClass = 'reachable';
      badgeText = '🟢 Verified Live (200)';
      if (ref.doi) {
        actionBtnHtml = `<a href="https://doi.org/${encodeURIComponent(ref.doi)}" target="_blank" class="btn-open-ext" title="Open article landing in new tab">Open ↗</a>`;
      }
    } else if (v.status === 'unreachable') {
      badgeClass = 'broken';
      badgeText = '❌ Unresolvable (404)';
    } else if (!v.status) {
      if (ref.doi) {
        badgeClass = 'registry';
        badgeText = '⏳ Auditing...';
      } else {
        badgeClass = 'registry';
        badgeText = '🔍 Searching DOI...';
      }
    }

    const titleDisplay = v.crossref_title || ref.title || ref.raw_text.slice(0, 75);
    const authorDisplay = (v.crossref_authors && v.crossref_authors.length > 0)
      ? v.crossref_authors.slice(0, 3).join(', ') + (v.crossref_authors.length > 3 ? ' et al.' : '')
      : (ref.authors.slice(0, 2).join(', ') || '—');

    const amaNum = (appState.amaMapping && appState.amaMapping[ref.ref_num]) || ref.ref_num;
    const isRenumbered = amaNum !== ref.ref_num;
    const renumberedTag = isRenumbered 
      ? `<br/><span style="display: inline-block; margin-top: 3px; font-size: 11px; background: #e0f2fe; color: #0369a1; padding: 1px 5px; border-radius: 3px; font-weight: 600;" title="Will be re-ordered to Reference #${amaNum}">→ AMA #${amaNum}</span>` 
      : '';

    tr.innerHTML = `
      <td class="ref-num-cell">[${ref.ref_num}]${renumberedTag}</td>
      <td>
        <strong>${titleDisplay}</strong><br/>
        <span style="color: var(--reading-ink-secondary); font-size: 12px;">${authorDisplay}</span>
        ${v.crossref_journal ? `<br/><em style="color: var(--editorial-plum); font-size: 12px;">${v.crossref_journal} (${v.crossref_year || ''})</em>` : ''}
      </td>
      <td>
        ${ref.doi ? `<a href="https://doi.org/${ref.doi}" target="_blank" style="color: var(--editorial-plum); word-break: break-all;">${ref.doi}</a> ${autoRecoveredPill}` : '<span style="color: var(--reading-ink-muted)">Missing</span>'}
      </td>
      <td style="white-space: nowrap;">
        <span class="badge-reach ${badgeClass}">${badgeText}</span>
        ${actionBtnHtml}
      </td>
      <td style="text-align: center; font-weight: 600;">
        ${m.occurrences.length}
      </td>
    `;
    tableBody.appendChild(tr);
  });
}

function updateAuditTableRow(refNum) {
  const tr = document.getElementById('ref-row-' + refNum);
  if (!tr || !appState.parsedData) return;
  const ref = appState.parsedData.references.find(r => r.ref_num === refNum);
  if (!ref) return;

  const v = appState.verdicts[refNum] || {};
  const m = (appState.mappings && appState.mappings[refNum]) || { occurrences: [] };

  let badgeClass = 'missing';
  let badgeText = 'No DOI';
  let actionBtnHtml = '';
  let autoRecoveredPill = '';

  if (v.status === 'recovered' || v.is_recovered) {
    badgeClass = 'recovered';
    badgeText = '🔍 DOI Recovered';
    const regSource = v.recovery_source || "Registry";
    autoRecoveredPill = `<span class="badge-auto-recovered" title="Automatically matched and verified via ${regSource}">Auto-Found (${regSource})</span>`;
    if (ref.doi) {
      actionBtnHtml = `<a href="https://doi.org/${encodeURIComponent(ref.doi)}" target="_blank" class="btn-open-ext" title="Verify auto-recovered DOI landing">Verify ↗</a>`;
    }
  } else if (v.status === 'bot_protected' || v.is_bot_gated) {
    badgeClass = 'bot-protected';
    badgeText = '🛡️ Bot Check / Paywall';
    if (ref.doi) {
      actionBtnHtml = `<a href="https://doi.org/${encodeURIComponent(ref.doi)}" target="_blank" class="btn-open-ext" title="Open directly in browser to view article or solve publisher verification">Verify ↗</a>`;
    }
  } else if (v.status === 'verified' || (v.is_reachable && !v.is_bot_gated)) {
    badgeClass = 'reachable';
    badgeText = '🟢 Verified Live (200)';
    if (ref.doi) {
      actionBtnHtml = `<a href="https://doi.org/${encodeURIComponent(ref.doi)}" target="_blank" class="btn-open-ext" title="Open article landing in new tab">Open ↗</a>`;
    }
  } else if (v.status === 'unreachable') {
    badgeClass = 'broken';
    badgeText = '❌ Unresolvable (404)';
  }

  const titleDisplay = v.crossref_title || ref.title || ref.raw_text.slice(0, 75);
  const authorDisplay = (v.crossref_authors && v.crossref_authors.length > 0)
    ? v.crossref_authors.slice(0, 3).join(', ') + (v.crossref_authors.length > 3 ? ' et al.' : '')
    : (ref.authors.slice(0, 2).join(', ') || '—');

  const amaNum = (appState.amaMapping && appState.amaMapping[ref.ref_num]) || ref.ref_num;
  const isRenumbered = amaNum !== ref.ref_num;
  const renumberedTag = isRenumbered 
    ? `<br/><span style="display: inline-block; margin-top: 3px; font-size: 11px; background: #e0f2fe; color: #0369a1; padding: 1px 5px; border-radius: 3px; font-weight: 600;" title="Will be re-ordered to Reference #${amaNum}">→ AMA #${amaNum}</span>` 
    : '';

  tr.innerHTML = `
    <td class="ref-num-cell">[${ref.ref_num}]${renumberedTag}</td>
    <td>
      <strong>${titleDisplay}</strong><br/>
      <span style="color: var(--reading-ink-secondary); font-size: 12px;">${authorDisplay}</span>
      ${v.crossref_journal ? `<br/><em style="color: var(--editorial-plum); font-size: 12px;">${v.crossref_journal} (${v.crossref_year || ''})</em>` : ''}
    </td>
    <td>
      ${ref.doi ? `<a href="https://doi.org/${ref.doi}" target="_blank" style="color: var(--editorial-plum); word-break: break-all;">${ref.doi}</a> ${autoRecoveredPill}` : '<span style="color: var(--reading-ink-muted)">Missing</span>'}
    </td>
    <td style="white-space: nowrap;">
      <span class="badge-reach ${badgeClass}">${badgeText}</span>
      ${actionBtnHtml}
    </td>
    <td style="text-align: center; font-weight: 600;">
      ${m.occurrences.length}
    </td>
  `;
  tr.classList.remove('row-auditing');
  tr.classList.add('row-updated');
  setTimeout(() => tr.classList.remove('row-updated'), 700);
}

function renderManuscriptExplorer() {
  manuscriptViewer.innerHTML = '';
  const { paraTexts, sites, refHdrIdx } = appState.parsedData;
  const scanEnd = (refHdrIdx !== -1) ? refHdrIdx : paraTexts.length;

  for (let pi = 0; pi < scanEnd; pi++) {
    const text = paraTexts[pi];
    if (!text.trim()) continue;

    const pDiv = document.createElement('div');
    pDiv.className = 'manuscript-paragraph';
    pDiv.dataset.paraIdx = pi;

    // Check if this paragraph contains citations
    const pSites = sites.filter(s => s.paragraph_idx === pi);

    if (pSites.length === 0) {
      pDiv.textContent = text;
    } else {
      let html = text;
      // Replace citation texts with interactive pills
      pSites.forEach(s => {
        const pill = `<span class="cit-pill" data-nums="${s.nums.join(',')}" title="Cited references: ${s.nums.join(', ')}">${s.text}</span>`;
        html = html.replace(s.text, pill);
      });
      pDiv.innerHTML = html;
    }

    manuscriptViewer.appendChild(pDiv);
  }

  // Add click listener for citation pills
  manuscriptViewer.querySelectorAll('.cit-pill').forEach(pill => {
    pill.addEventListener('click', (e) => {
      const nums = e.target.dataset.nums.split(',').map(n => parseInt(n, 10));
      if (nums.length > 0) {
        updateActiveReferenceCard(nums[0]);
      }
    });
  });
}

function updateActiveReferenceCard(refNum) {
  appState.selectedRefNum = refNum;
  const { references } = appState.parsedData;
  const ref = references.find(r => r.ref_num === refNum);
  if (!ref) return;

  const v = appState.verdicts[refNum] || {};
  const m = appState.mappings[refNum] || { occurrences: [] };

  const sentencesHtml = m.occurrences.length > 0
    ? m.occurrences.map((occ, idx) => `
        <li style="margin-bottom: 10px; font-size: 13px; line-height: 1.5;">
          <strong>Mention ${idx + 1} (Para ${occ.paragraphIdx + 1}):</strong><br/>
          <span style="font-family: var(--font-reading); color: var(--reading-ink-primary);">"${occ.sentence}"</span>
        </li>
      `).join('')
    : '<li style="color: var(--status-broken);">⚠️ Not cited anywhere in body text.</li>';

  let statusBadgeText = '🟢 Verified Live';
  let statusBadgeClass = 'reachable';
  let explanationBox = '';

  if (v.status === 'recovered' || v.is_recovered) {
    statusBadgeText = '🔍 DOI Recovered';
    statusBadgeClass = 'recovered';
    const regSource = v.recovery_source || "Registry";
    explanationBox = `
      <div style="background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534; padding: 10px 14px; font-size: 12px; margin-bottom: 14px; line-height: 1.5; border-radius: 4px;">
        <strong>🔍 Auto-Recovered Missing DOI:</strong><br/>
        This reference lacked a DOI in the original manuscript. The multi-registry search engine located and verified this article in <strong>${regSource}</strong> with active DOI <code>${ref.doi}</code>.<br/>
        <em>✓ The recovered DOI has been automatically inserted into your Word deliverables and linked in your Zotero export.</em>
      </div>
    `;
  } else if (v.status === 'bot_protected' || v.is_bot_gated) {
    statusBadgeText = '🛡️ Bot Check / Paywall';
    statusBadgeClass = 'bot-protected';
    explanationBox = `
      <div style="background: #fffbeb; border: 1px solid #fde68a; color: #92400e; padding: 10px 14px; font-size: 12px; margin-bottom: 14px; line-height: 1.5;">
        <strong>🛡️ Publisher Anti-Bot / Paywall Notice:</strong><br/>
        This DOI is officially registered and active in the International DOI Foundation Handle registry. The publisher landing page (Elsevier, Springer Nature, Oxford Academic, RSNA, etc.) challenges automated web scrapers with Cloudflare Turnstile, bot verification, or institutional paywalls.<br/>
        <em>✓ This paper is completely valid, fully accessible to human readers in standard web browsers, and is securely linked in your Zotero export.</em>
      </div>
    `;
  } else if (v.status === 'unreachable') {
    statusBadgeText = '❌ Unresolvable (404)';
    statusBadgeClass = 'broken';
  } else if (v.status === 'missing_doi') {
    statusBadgeText = '⚠️ Missing DOI';
    statusBadgeClass = 'missing';
  }

  activeRefCard.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
      <h3 style="font-family: var(--font-headline); color: var(--color-ink); font-size: 18px;">
        [${ref.ref_num}] ${v.crossref_title || ref.title || 'Untitled Reference'}
      </h3>
      <span class="badge-reach ${statusBadgeClass}">
        ${statusBadgeText}
      </span>
    </div>
    
    <div style="font-size: 13px; margin-bottom: 14px; color: var(--color-ink-light);">
      <strong>Authors:</strong> ${(v.crossref_authors || ref.authors || []).join(', ') || 'Unknown'}<br/>
      <strong>Journal:</strong> ${v.crossref_journal || ref.journal || '—'} &bull; 
      <strong>Year:</strong> ${v.crossref_year || ref.year || '—'} &bull; 
      <strong>Volume:</strong> ${v.crossref_volume || ref.volume || '—'} (${v.crossref_issue || '—'}): ${v.crossref_pages || '—'}<br/>
      <strong>DOI:</strong> ${ref.doi ? `<a href="https://doi.org/${encodeURIComponent(ref.doi)}" target="_blank" style="color: var(--color-accent);">${ref.doi}</a>` : 'None'}
    </div>

    ${explanationBox}

    ${v.resolved_url ? `
      <div style="background: var(--color-paper-dark); padding: 8px 12px; border: 1px solid var(--color-rule-light); font-size: 12px; margin-bottom: 14px; word-break: break-all;">
        <strong>Live Publisher Target:</strong> <a href="${v.resolved_url}" target="_blank" style="color: var(--color-ink);">${v.resolved_url}</a>
        <a href="https://doi.org/${encodeURIComponent(ref.doi)}" target="_blank" class="btn-open-ext" style="margin-left: 8px;">Open in Browser ↗</a>
      </div>
    ` : ''}

    <h4 style="font-family: var(--font-headline); font-size: 14px; color: var(--color-ink); margin-bottom: 8px; border-top: 1px solid var(--color-rule-light); padding-top: 10px;">
      In-Manuscript Sentence Occurrences (${m.occurrences.length})
    </h4>
    <ul style="list-style: none; padding-left: 0;">
      ${sentencesHtml}
    </ul>
  `;
}

function highlightSentenceInManuscript(refNum) {
  const m = appState.mappings[refNum];
  if (!m || m.occurrences.length === 0) return;

  const firstPara = m.occurrences[0].paragraphIdx;
  const pEl = manuscriptViewer.querySelector(`[data-para-idx="${firstPara}"]`);
  if (pEl) {
    pEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    pEl.style.transition = 'background 0.3s ease';
    pEl.style.backgroundColor = '#fff2db';
    setTimeout(() => {
      pEl.style.backgroundColor = 'transparent';
    }, 1800);
  }
}

// ---------------- Deliverables Center & Audit Report Modal ----------------

const btnViewAuditReport = document.getElementById('btnViewAuditReport');
const auditReportModal = document.getElementById('auditReportModal');
const auditReportModalBody = document.getElementById('auditReportModalBody');
const btnCloseAuditModal = document.getElementById('btnCloseAuditModal');
const btnCloseAuditModalFooter = document.getElementById('btnCloseAuditModalFooter');
const btnCopyAuditReport = document.getElementById('btnCopyAuditReport');
const btnPrintAuditReport = document.getElementById('btnPrintAuditReport');

function generateAuditReportHtml() {
  if (!appState.parsedData) return "<p>No manuscript audited yet. Upload a .docx manuscript to generate a complete verification report.</p>";
  const { references, sites } = appState.parsedData;
  const reachableCount = metricReachable.textContent;
  const botCount = metricBotGated ? metricBotGated.textContent : "0";
  const brokenCount = metricBroken.textContent;
  const seqText = metricSequence.textContent || "Consecutive (Valid 1..N)";

  let html = `
    <div style="margin-bottom: 20px; padding: 16px 20px; background: #faf7f9; border: 1px solid var(--border-outline); border-radius: 6px;">
      <h3 style="margin-top: 0; color: var(--primary-wine); font-family: var(--font-headline); font-size: 1.15rem;">Manuscript: ${appState.fileName}</h3>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-top: 12px; font-size: 12px;">
        <div><strong>Total In-Text Citations:</strong> ${sites.length}</div>
        <div><strong>Bibliography References:</strong> ${references.length}</div>
        <div><strong>Live Reachable:</strong> <span style="color: #16a34a; font-weight: 600;">${reachableCount}</span></div>
        <div><strong>Bot Protected / Paywall:</strong> <span style="color: #b45309; font-weight: 600;">${botCount}</span></div>
        <div><strong>Unresolvable (404):</strong> <span style="color: #dc2626; font-weight: 600;">${brokenCount}</span></div>
        <div><strong>AMA Sequence:</strong> ${seqText}</div>
      </div>
    </div>

    <h4 style="font-family: var(--font-headline); color: var(--primary-wine); font-size: 1.05rem; margin-top: 1.4rem;">Scholarly Reference Audit & Reachability Findings</h4>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Bibliographic Record</th>
          <th>DOI Identifier</th>
          <th>Verification Status</th>
          <th style="text-align: center;">In-Text Mentions</th>
        </tr>
      </thead>
      <tbody>
  `;

  references.forEach(r => {
    const v = appState.verdicts[r.ref_num] || {};
    const m = (appState.mappings && appState.mappings[r.ref_num]) || { occurrences: [] };
    const amaNum = (appState.amaMapping && appState.amaMapping[r.ref_num]) || r.ref_num;
    const numDisplay = (amaNum === r.ref_num) ? `[${r.ref_num}]` : `[${r.ref_num}] → AMA #${amaNum}`;
    const doiDisplay = r.doi ? `<a href="https://doi.org/${encodeURIComponent(r.doi)}" target="_blank" style="color: var(--editorial-plum);">${r.doi}</a>` : '<span style="color: #9ca3af;">Missing</span>';
    
    let statusBadge = '<span class="badge-reach missing">No DOI</span>';
    if (v.status === 'recovered' || v.is_recovered) {
      statusBadge = '<span class="badge-reach recovered">🔍 DOI Recovered</span>';
    } else if (v.status === 'bot_protected' || v.is_bot_gated) {
      statusBadge = '<span class="badge-reach bot-protected">🛡️ Bot Check / Paywall</span>';
    } else if (v.status === 'verified' || (v.is_reachable && !v.is_bot_gated)) {
      statusBadge = '<span class="badge-reach reachable">🟢 Verified Live</span>';
    } else if (v.status === 'unreachable') {
      statusBadge = '<span class="badge-reach broken">❌ Unresolvable (404)</span>';
    }

    const titleDisplay = v.crossref_title || r.title || r.raw_text.slice(0, 80);
    const authorDisplay = (v.crossref_authors && v.crossref_authors.length > 0)
      ? v.crossref_authors.slice(0, 3).join(', ') + (v.crossref_authors.length > 3 ? ' et al.' : '')
      : (r.authors.slice(0, 2).join(', ') || '—');

    html += `
      <tr>
        <td style="font-weight: 600; white-space: nowrap;">${numDisplay}</td>
        <td>
          <strong>${titleDisplay}</strong><br/>
          <span style="font-size: 11px; color: #62535d;">${authorDisplay}</span>
          ${v.crossref_journal ? `<br/><em style="color: #814d75; font-size: 11px;">${v.crossref_journal} (${v.crossref_year || ''})</em>` : ''}
        </td>
        <td style="word-break: break-all; font-size: 11px;">${doiDisplay}</td>
        <td>${statusBadge}</td>
        <td style="text-align: center; font-weight: 600;">${m.occurrences.length}x</td>
      </tr>
    `;
  });

  html += `
      </tbody>
    </table>
  `;
  return html;
}

if (btnViewAuditReport) {
  btnViewAuditReport.addEventListener('click', () => {
    if (!appState.parsedData) {
      alert("Please upload or load a manuscript first.");
      return;
    }
    auditReportModalBody.innerHTML = generateAuditReportHtml();
    auditReportModal.style.display = 'flex';
  });
}

if (btnCloseAuditModal) {
  btnCloseAuditModal.addEventListener('click', () => {
    auditReportModal.style.display = 'none';
  });
}

if (btnCloseAuditModalFooter) {
  btnCloseAuditModalFooter.addEventListener('click', () => {
    auditReportModal.style.display = 'none';
  });
}

if (auditReportModal) {
  auditReportModal.addEventListener('click', (e) => {
    if (e.target === auditReportModal) {
      auditReportModal.style.display = 'none';
    }
  });
}

if (btnCopyAuditReport) {
  btnCopyAuditReport.addEventListener('click', async () => {
    if (!appState.parsedData) return;
    const { references } = appState.parsedData;
    const reportLines = [
      `# Co-Scientist Reference Audit Report: ${appState.fileName}`,
      `Generated by Co-Scientist Reference Auditor & Zotero Linker`,
      ``,
      `## Summary Metrics`,
      `- Total In-Text Citations: ${appState.parsedData.sites.length}`,
      `- Total Bibliography References: ${references.length}`,
      `- Live Reachable: ${metricReachable.textContent}`,
      `- Consecutive First-Mention Order: ${metricSequence.textContent}`,
      ``,
      `## Reference Verification Findings`
    ];

    references.forEach(r => {
      const v = appState.verdicts[r.ref_num] || {};
      const m = (appState.mappings && appState.mappings[r.ref_num]) || { occurrences: [] };
      reportLines.push(`### [${r.ref_num}] ${v.crossref_title || r.title || r.raw_text.slice(0, 60)}`);
      reportLines.push(`- **DOI:** ${r.doi || 'None'}`);
      reportLines.push(`- **Status:** ${v.is_reachable ? 'Reachable (200 OK)' : 'Broken / Unreachable'}`);
      if (v.is_recovered) reportLines.push(`- **DOI Auto-Recovery:** Found via ${v.recovery_source || 'Registry'}: ${v.recovered_doi}`);
      if (v.resolved_url) reportLines.push(`- **Target URL:** ${v.resolved_url}`);
      reportLines.push(`- **Manuscript Citations:** ${m.occurrences.length} time(s)`);
      if (m.firstMentionSentence) reportLines.push(`- **Context:** "${m.firstMentionSentence}"`);
      reportLines.push('');
    });

    try {
      await navigator.clipboard.writeText(reportLines.join('\n'));
      btnCopyAuditReport.textContent = '✓ Copied to Clipboard!';
      setTimeout(() => { btnCopyAuditReport.textContent = '📋 Copy Report to Clipboard'; }, 2000);
    } catch (err) {
      alert("Failed to copy to clipboard: " + err.message);
    }
  });
}

if (btnPrintAuditReport) {
  btnPrintAuditReport.addEventListener('click', () => {
    const printWindow = window.open('', '_blank');
    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>Reference Audit Report - ${appState.fileName}</title>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Georgia, serif; padding: 25px; color: #1a0017; }
          h3, h4 { color: #3a0f34; }
          table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 12px; }
          th, td { border: 1px solid #d2c2cb; padding: 6px 10px; text-align: left; }
          th { background: #3a0f34; color: #fff; }
          tr:nth-child(even) { background: #fbf9f4; }
        </style>
      </head>
      <body>
        ${generateAuditReportHtml()}
      </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => {
      printWindow.print();
      printWindow.close();
    }, 300);
  });
}

if (btnDownloadTrackedDocx) {
  btnDownloadTrackedDocx.addEventListener('click', async () => {
    if (!appState.parsedData) return;
    try {
      btnDownloadTrackedDocx.textContent = '⏳ Generating Tracked Changes...';
      const blob = await injectZoteroFieldsInBrowser(appState.parsedData, appState.verdicts, true, true, "Co-Scientist");
      const baseName = appState.fileName.replace(/\.docx$/i, '');
      downloadBlob(blob, `${baseName}_tracked_changes.docx`);
      btnDownloadTrackedDocx.textContent = '📝 Download Tracked Changes (.docx)';
    } catch (err) {
      alert("Error generating Tracked Changes document: " + err.message);
      btnDownloadTrackedDocx.textContent = '📝 Download Tracked Changes (.docx)';
    }
  });
}

btnDownloadDocx.addEventListener('click', async () => {
  if (!appState.parsedData) return;
  try {
    btnDownloadDocx.textContent = '⏳ Injecting & Re-ordering...';
    const blob = await injectZoteroFieldsInBrowser(appState.parsedData, appState.verdicts, true, false);
    const baseName = appState.fileName.replace(/\.docx$/i, '');
    downloadBlob(blob, `${baseName}_zotero_linked.docx`);
    btnDownloadDocx.textContent = '📄 Download Clean Linked (.docx)';
  } catch (err) {
    alert("Error generating linked Word document: " + err.message);
    btnDownloadDocx.textContent = '📄 Download Clean Linked (.docx)';
  }
});

btnDownloadRis.addEventListener('click', () => {
  if (!appState.parsedData) return;
  const risText = generateClientRis(appState.parsedData.references, appState.verdicts, appState.amaMapping);
  const blob = new Blob([risText], { type: 'application/x-research-info-systems' });
  const baseName = appState.fileName.replace(/\.docx$/i, '');
  downloadBlob(blob, `${baseName}_references.ris`);
});

btnDownloadReport.addEventListener('click', () => {
  if (!appState.parsedData) return;
  const { references } = appState.parsedData;
  const reportLines = [
    `# Co-Scientist Reference Audit Report: ${appState.fileName}`,
    `Generated by Co-Scientist Reference Auditor & Zotero Linker`,
    ``,
    `## Summary Metrics`,
    `- Total In-Text Citations: ${appState.parsedData.sites.length}`,
    `- Total Bibliography References: ${references.length}`,
    `- Consecutive First-Mention Order: ${metricSequence.textContent}`,
    ``,
    `## Reference Verification Findings`
  ];

  references.forEach(r => {
    const v = appState.verdicts[r.ref_num] || {};
    const m = appState.mappings[r.ref_num] || { occurrences: [] };
    reportLines.push(`### [${r.ref_num}] ${v.crossref_title || r.title || r.raw_text.slice(0, 60)}`);
    reportLines.push(`- **DOI:** ${r.doi || 'None'}`);
    reportLines.push(`- **Status:** ${v.is_reachable ? 'Reachable (200 OK)' : 'Broken / Unreachable'}`);
    if (v.resolved_url) reportLines.push(`- **Target URL:** ${v.resolved_url}`);
    reportLines.push(`- **Manuscript Citations:** ${m.occurrences.length} time(s)`);
    if (m.firstMentionSentence) reportLines.push(`- **Context:** "${m.firstMentionSentence}"`);
    reportLines.push('');
  });

  const blob = new Blob([reportLines.join('\n')], { type: 'text/markdown' });
  const baseName = appState.fileName.replace(/\.docx$/i, '');
  downloadBlob(blob, `${baseName}_audit_report.md`);
});

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

