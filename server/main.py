"""
FastAPI Server for Co-Scientist Reference Auditor & Zotero Linker.
"""
import os
import uuid
from io import BytesIO
from typing import Dict, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from server.models import AuditSummary, ReferenceEntry, CitationSite, ValidationVerdict, JobStatus, JobRecord
from server.parser import parse_docx_manuscript, parse_paragraphs_list
from server.validator import validate_single_reference, map_usage_and_sequence
from server.ris_generator import generate_ris
from server.linker import link_docx_manuscript, build_ama_renumbering_map

app = FastAPI(
    title="Co-Scientist Reference Auditor & Zotero Linker",
    description="Live reference reachability verification, in-manuscript citation mapping, and native Zotero field injection.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    index_path = os.path.join(os.path.dirname(__file__), "..", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Co-Scientist Reference Auditor API is running."}

@app.get("/sample_radiology_manuscript.docx")
def serve_sample_doc():
    sample_path = os.path.join(os.path.dirname(__file__), "..", "sample_radiology_manuscript.docx")
    if os.path.exists(sample_path):
        return FileResponse(sample_path)
    raise HTTPException(status_code=404, detail="Sample manuscript not found.")

@app.get("/ACTA2_Manuscript_11.14.2026.docx")
def serve_acta2_doc():
    doc_path = os.path.join(os.path.dirname(__file__), "..", "ACTA2_Manuscript_11.14.2026.docx")
    if os.path.exists(doc_path):
        return FileResponse(doc_path)
    raise HTTPException(status_code=404, detail="ACTA2 manuscript not found.")

JOBS_CACHE: Dict[str, JobRecord] = {}

def execute_job_linking(job: JobRecord):
    """Guarded execution of linking for a job."""
    if not job.file_bytes:
        raise HTTPException(status_code=400, detail="Linking requires an uploaded .docx file.")
    
    if job.status not in (JobStatus.AUDITED, JobStatus.READY):
        raise HTTPException(status_code=409, detail=f"Job cannot be linked in status '{job.status.value}'")

    job.transition_to(JobStatus.LINKING)
    try:
        clean_stream = BytesIO()
        link_docx_manuscript(
            docx_input=BytesIO(job.file_bytes),
            sites=job.sites,
            references=job.references,
            verdicts=job.verdicts,
            output_target=clean_stream,
            renumber_ama=True,
            track_changes=False
        )
        job.linked_bytes = clean_stream.getvalue()

        tracked_stream = BytesIO()
        link_docx_manuscript(
            docx_input=BytesIO(job.file_bytes),
            sites=job.sites,
            references=job.references,
            verdicts=job.verdicts,
            output_target=tracked_stream,
            renumber_ama=True,
            track_changes=True,
            author="Co-Scientist"
        )
        job.tracked_bytes = tracked_stream.getvalue()
        job.ris_text = generate_ris(job.references, job.verdicts, mapping=job.mapping)
        job.transition_to(JobStatus.READY)
    except Exception as e:
        job.error_message = str(e)
        job.transition_to(JobStatus.ERROR)
        raise HTTPException(status_code=500, detail=f"Failed to link manuscript: {str(e)}")

@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "service": "Co-Scientist Reference Auditor & Zotero Linker",
        "version": "1.0.0"
    }

@app.post("/api/audit")
async def audit_manuscript(
    file: Optional[UploadFile] = File(None),
    text_content: Optional[str] = Form(None),
    citation_format: str = Form("auto")
):
    job_id = str(uuid.uuid4())
    filename = "manuscript.docx"
    file_bytes = None

    job = JobRecord(job_id=job_id, status=JobStatus.INITIALIZED, filename=filename)
    JOBS_CACHE[job_id] = job
    job.transition_to(JobStatus.PARSING)

    if file:
        filename = file.filename
        job.filename = filename
        file_bytes = await file.read()
        job.file_bytes = file_bytes
        try:
            paras, sites, references = parse_docx_manuscript(BytesIO(file_bytes), citation_format=citation_format)
        except Exception as e:
            job.error_message = f"Failed to parse docx: {str(e)}"
            job.transition_to(JobStatus.ERROR)
            raise HTTPException(status_code=400, detail=f"Failed to parse docx: {str(e)}")
    elif text_content:
        filename = "pasted_manuscript.txt"
        job.filename = filename
        para_lines = [p.strip() for p in text_content.split("\n\n") if p.strip()]
        paras, sites, references = parse_paragraphs_list(para_lines, citation_format=citation_format)
    else:
        job.error_message = "Must provide either a .docx file or text_content."
        job.transition_to(JobStatus.ERROR)
        raise HTTPException(status_code=400, detail="Must provide either a .docx file or text_content.")

    # Run validation & reachability concurrently on all references
    verdicts: Dict[int, ValidationVerdict] = {}
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ref = {executor.submit(validate_single_reference, ref): ref for ref in references}
        for future in as_completed(future_to_ref):
            ref = future_to_ref[future]
            try:
                verdicts[ref.ref_num] = future.result()
            except Exception as e:
                verdicts[ref.ref_num] = ValidationVerdict(ref_num=ref.ref_num, status="error", notes=[str(e)])

    # Map usage and AMA order
    mappings, seq_valid, warnings = map_usage_and_sequence(references, sites)

    total_verified_live = sum(1 for v in verdicts.values() if v.status == "verified")
    total_bot_protected = sum(1 for v in verdicts.values() if v.status == "bot_protected")
    total_recovered = sum(1 for v in verdicts.values() if v.status == "recovered" or v.is_recovered_doi)
    total_reachable = total_verified_live + total_bot_protected + total_recovered
    total_broken = sum(1 for v in verdicts.values() if v.status == "unreachable")
    total_missing = sum(1 for v in verdicts.values() if v.status == "missing_doi")

    summary = AuditSummary(
        filename=filename,
        total_citations=len(sites),
        total_references=len(references),
        total_reachable=total_reachable,
        total_verified_live=total_verified_live,
        total_bot_protected=total_bot_protected,
        total_recovered_doi=total_recovered,
        total_broken=total_broken,
        total_missing_doi=total_missing,
        consecutive_order_valid=seq_valid,
        order_warnings=warnings,
        sites=sites,
        references=references,
        verdicts=verdicts,
        mappings=mappings
    )

    # Calculate AMA Sequential Renumbering Map
    mapping, first_seen_order, uncited = build_ama_renumbering_map(references, sites)

    job.summary = summary
    job.paras = paras
    job.sites = sites
    job.references = references
    job.verdicts = verdicts
    job.mappings = mappings
    job.mapping = mapping
    job.first_seen_order = first_seen_order
    job.uncited = uncited
    job.transition_to(JobStatus.AUDITED)

    return {"job_id": job_id, "summary": summary, "ama_mapping": mapping, "status": job.status.value}

@app.post("/api/link/{job_id}")
async def link_manuscript(job_id: str):
    if job_id not in JOBS_CACHE:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    
    job = JOBS_CACHE[job_id]
    execute_job_linking(job)

    return {
        "job_id": job_id,
        "status": job.status.value,
        "download_docx": f"/api/download/{job_id}/docx",
        "download_tracked_docx": f"/api/download/{job_id}/tracked_docx",
        "download_ris": f"/api/download/{job_id}/ris",
        "download_report": f"/api/download/{job_id}/report"
    }

@app.get("/api/download/{job_id}/docx")
def download_docx(job_id: str, mode: Optional[str] = None):
    if job_id not in JOBS_CACHE:
        raise HTTPException(status_code=404, detail="Job not found.")

    job = JOBS_CACHE[job_id]
    if job.status == JobStatus.AUDITED:
        execute_job_linking(job)
    elif job.status == JobStatus.ERROR:
        raise HTTPException(status_code=409, detail=f"Job failed with error: {job.error_message}")
    elif job.status != JobStatus.READY:
        raise HTTPException(status_code=409, detail=f"Job is not ready. Status: {job.status.value}")

    if mode == "tracked" and job.tracked_bytes:
        content = job.tracked_bytes
        suffix = "tracked_changes"
    elif job.linked_bytes:
        content = job.linked_bytes
        suffix = "zotero_linked"
    else:
        raise HTTPException(status_code=404, detail="Linked file not ready.")

    orig_name = job.filename
    base = os.path.splitext(orig_name)[0]
    out_name = f"{base}_{suffix}.docx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'}
    )

@app.get("/api/download/{job_id}/tracked_docx")
def download_tracked_docx(job_id: str):
    if job_id not in JOBS_CACHE:
        raise HTTPException(status_code=404, detail="Job not found.")

    job = JOBS_CACHE[job_id]
    if job.status == JobStatus.AUDITED:
        execute_job_linking(job)
    elif job.status == JobStatus.ERROR:
        raise HTTPException(status_code=409, detail=f"Job failed with error: {job.error_message}")
    elif job.status != JobStatus.READY:
        raise HTTPException(status_code=409, detail=f"Job is not ready. Status: {job.status.value}")

    if not job.tracked_bytes:
        raise HTTPException(status_code=404, detail="Tracked changes file not ready.")

    orig_name = job.filename
    base = os.path.splitext(orig_name)[0]
    out_name = f"{base}_tracked_changes.docx"
    return Response(
        content=job.tracked_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'}
    )

@app.get("/api/download/{job_id}/ris")
def download_ris(job_id: str):
    if job_id not in JOBS_CACHE:
        raise HTTPException(status_code=404, detail="Job not found.")
    
    job = JOBS_CACHE[job_id]
    if job.status == JobStatus.AUDITED:
        execute_job_linking(job)

    ris_content = job.ris_text or generate_ris(job.references, job.verdicts, mapping=job.mapping)
    base = os.path.splitext(job.filename)[0]
    return Response(
        content=ris_content,
        media_type="application/x-research-info-systems",
        headers={"Content-Disposition": f'attachment; filename="{base}_references.ris"'}
    )

@app.get("/api/download/{job_id}/report")
def download_report(job_id: str):
    if job_id not in JOBS_CACHE:
        raise HTTPException(status_code=404, detail="Job not found.")
    job = JOBS_CACHE[job_id]
    summary: AuditSummary = job.summary

    lines = [
        f"# Co-Scientist Reference Audit Report: {summary.filename}",
        f"**Status:** {'PASS' if summary.consecutive_order_valid and summary.total_broken == 0 else 'ATTENTION REQUIRED'}",
        f"- Total In-Text Citation Sites: {summary.total_citations}",
        f"- Total Bibliography References: {summary.total_references}",
        f"- Verified & Reachable DOIs: {summary.total_reachable}",
        f"- Broken / Unreachable DOIs: {summary.total_broken}",
        f"- References Missing DOIs: {summary.total_missing_doi}",
        f"- AMA Consecutive Order: {'VALID' if summary.consecutive_order_valid else 'WARNINGS DETECTED'}",
        "",
        "## Order & Formatting Warnings"
    ]
    if summary.order_warnings:
        for w in summary.order_warnings:
            lines.append(f"- ⚠️ {w}")
    else:
        lines.append("- ✓ All references appear consecutively in order of first mention.")

    lines.append("\n## Reference Audit Details")
    for r in summary.references:
        v = summary.verdicts.get(r.ref_num)
        m = summary.mappings.get(r.ref_num)
        reach_badge = "🟢 Reachable (200 OK)" if (v and v.is_reachable) else "🔴 Unreachable"
        lines.append(f"\n### [{r.ref_num}] {r.title or r.raw_text[:70]}")
        lines.append(f"- **DOI:** {r.doi or 'None'}")
        lines.append(f"- **Reachability:** {reach_badge}")
        if v and v.resolved_url:
            lines.append(f"- **Resolved Destination:** {v.resolved_url}")
        if m:
            lines.append(f"- **Total In-Text Citations:** {m.total_occurrences}")
            lines.append(f"- **First Cited Context:** \"{m.first_mention_sentence}\"")
        if v and v.notes:
            lines.append("- **Audit Notes:** " + " | ".join(v.notes))

    base = os.path.splitext(job.filename)[0]
    return Response(
        content="\n".join(lines),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{base}_audit_report.md"'}
    )

@app.get("/api/sample")
def get_sample_manuscript():
    sample_path = "sample_radiology_manuscript.docx"
    if os.path.exists(sample_path):
        with open(sample_path, "rb") as f:
            bytes_data = f.read()
        return Response(
            content=bytes_data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": 'attachment; filename="sample_radiology_manuscript.docx"'}
        )
    raise HTTPException(status_code=404, detail="Sample manuscript file not generated yet.")
