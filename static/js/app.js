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

// DOM Elements
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const btnSample = document.getElementById('btnSample');
const resultsSection = document.getElementById('resultsSection');
const tableBody = document.getElementById('referencesTableBody');
const manuscriptViewer = document.getElementById('manuscriptViewer');
const activeRefCard = document.getElementById('activeRefCard');

// Metrics
const metricCitations = document.getElementById('metricCitations');
const metricReferences = document.getElementById('metricReferences');
const metricReachable = document.getElementById('metricReachable');
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

if (dropzone && fileInput) {
  dropzone.addEventListener('click', () => fileInput.click());

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelected(e.target.files[0]);
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
      btnSample.textContent = '📄 Load Sample Radiology Manuscript';
    } catch (err) {
      alert("Error loading sample: " + err.message);
      btnSample.textContent = '📄 Load Sample Radiology Manuscript';
    }
  });
}

// ---------------- Pipeline Execution ----------------

async function handleFileSelected(file) {
  if (!file.name.toLowerCase().endsWith('.docx')) {
    alert("Please upload a Microsoft Word document (.docx).");
    return;
  }

  appState.currentFile = file;
  appState.fileName = file.name;
  appState.fsmState = 'PARSING';
  setStepper('parse');

  resultsSection.style.display = 'block';
  resultsSection.scrollIntoView({ behavior: 'smooth' });

  // 1. In-Browser Parse
  try {
    const parsed = await parseDocxFile(file);
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

  appState.verdicts = {};
  let reachableCount = 0;
  let brokenCount = 0;

  // Process references concurrently
  const validationPromises = appState.parsedData.references.map(async (ref) => {
    const verdict = await validateReferenceCrossref(ref.doi);
    appState.verdicts[ref.ref_num] = verdict;
    if (verdict.is_reachable) reachableCount++;
    else if (verdict.status === 'unreachable') brokenCount++;
    metricReachable.textContent = reachableCount;
    metricBroken.textContent = brokenCount;
  });

  await Promise.all(validationPromises);

  // 3. Sentence & Usage Mapping
  appState.fsmState = 'MAPPING';
  setStepper('mapping');
  computeUsageMappings();

  // 4. Render UI
  renderAuditTable();
  renderManuscriptExplorer();
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

  metricSequence.textContent = seqValid ? "Consecutive (Valid)" : "Warnings Detected";
  metricSequence.style.color = seqValid ? "var(--status-reachable)" : "var(--status-broken)";

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
    const m = appState.mappings[ref.ref_num] || { occurrences: [] };

    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    tr.addEventListener('click', () => {
      updateActiveReferenceCard(ref.ref_num);
      highlightSentenceInManuscript(ref.ref_num);
    });

    let badgeClass = 'missing';
    let badgeText = 'No DOI';
    if (v.is_reachable) {
      badgeClass = 'reachable';
      badgeText = 'Reachable (200 OK)';
    } else if (v.status === 'unreachable') {
      badgeClass = 'broken';
      badgeText = 'Broken Link (404)';
    }

    const titleDisplay = v.crossref_title || ref.title || ref.raw_text.slice(0, 75);
    const authorDisplay = (v.crossref_authors && v.crossref_authors.length > 0)
      ? v.crossref_authors.slice(0, 3).join(', ') + (v.crossref_authors.length > 3 ? ' et al.' : '')
      : (ref.authors.slice(0, 2).join(', ') || '—');

    tr.innerHTML = `
      <td class="ref-num-cell">[${ref.ref_num}]</td>
      <td>
        <strong>${titleDisplay}</strong><br/>
        <span style="color: var(--reading-ink-secondary); font-size: 12px;">${authorDisplay}</span>
        ${v.crossref_journal ? `<br/><em style="color: var(--editorial-plum); font-size: 12px;">${v.crossref_journal} (${v.crossref_year || ''})</em>` : ''}
      </td>
      <td>
        ${ref.doi ? `<a href="https://doi.org/${ref.doi}" target="_blank" style="color: var(--editorial-plum); word-break: break-all;">${ref.doi}</a>` : '<span style="color: var(--reading-ink-muted)">Missing</span>'}
      </td>
      <td>
        <span class="badge-reach ${badgeClass}">${badgeText}</span>
      </td>
      <td style="text-align: center; font-weight: 600;">
        ${m.occurrences.length}
      </td>
    `;
    tableBody.appendChild(tr);
  });
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

  activeRefCard.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
      <h3 style="font-family: var(--font-serif); color: var(--primary-wine); font-size: 18px;">
        [${ref.ref_num}] ${v.crossref_title || ref.title || 'Untitled Reference'}
      </h3>
      <span class="badge-reach ${v.is_reachable ? 'reachable' : 'broken'}">
        ${v.is_reachable ? 'Reachable' : 'Broken'}
      </span>
    </div>
    
    <div style="font-size: 13px; margin-bottom: 14px; color: var(--reading-ink-secondary);">
      <strong>Authors:</strong> ${(v.crossref_authors || ref.authors || []).join(', ') || 'Unknown'}<br/>
      <strong>Journal:</strong> ${v.crossref_journal || ref.journal || '—'} &bull; 
      <strong>Year:</strong> ${v.crossref_year || ref.year || '—'} &bull; 
      <strong>Volume:</strong> ${v.crossref_volume || ref.volume || '—'} (${v.crossref_issue || '—'}): ${v.crossref_pages || '—'}<br/>
      <strong>DOI:</strong> ${ref.doi ? `<a href="https://doi.org/${ref.doi}" target="_blank" style="color: var(--editorial-plum);">${ref.doi}</a>` : 'None'}
    </div>

    ${v.resolved_url ? `
      <div style="background: #f7f3f6; padding: 8px 12px; border-radius: 4px; font-size: 12px; margin-bottom: 14px; word-break: break-all;">
        <strong>Live Publisher Target:</strong> <a href="${v.resolved_url}" target="_blank" style="color: var(--primary-wine);">${v.resolved_url}</a>
      </div>
    ` : ''}

    <h4 style="font-family: var(--font-serif); font-size: 14px; color: var(--primary-wine); margin-bottom: 8px; border-top: 1px solid var(--border-outline); padding-top: 10px;">
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

// ---------------- Deliverables Center ----------------

btnDownloadDocx.addEventListener('click', async () => {
  if (!appState.parsedData) return;
  try {
    btnDownloadDocx.textContent = '⏳ Injecting Fields...';
    const blob = await injectZoteroFieldsInBrowser(appState.parsedData, appState.verdicts);
    const baseName = appState.fileName.replace(/\.docx$/i, '');
    downloadBlob(blob, `${baseName}_zotero_linked.docx`);
    btnDownloadDocx.textContent = '📥 Download Zotero-Linked (.docx)';
  } catch (err) {
    alert("Error generating linked Word document: " + err.message);
    btnDownloadDocx.textContent = '📥 Download Zotero-Linked (.docx)';
  }
});

btnDownloadRis.addEventListener('click', () => {
  if (!appState.parsedData) return;
  const risText = generateClientRis(appState.parsedData.references, appState.verdicts);
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
