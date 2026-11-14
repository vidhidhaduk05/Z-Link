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

from server.models import AuditSummary, ReferenceEntry, CitationSite, ValidationVerdict
from server.parser import parse_docx_manuscript, parse_paragraphs_list
from server.validator import validate_single_reference, map_usage_and_sequence
from server.ris_generator import generate_ris
from server.linker import link_docx_manuscript

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

JOBS_CACHE: Dict[str, Dict] = {}

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
    text_content: Optional[str] = Form(None)
):
    job_id = str(uuid.uuid4())
    filename = "manuscript.docx"
    file_bytes = None

    if file:
        filename = file.filename
        file_bytes = await file.read()
        try:
            paras, sites, references = parse_docx_manuscript(BytesIO(file_bytes))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse docx: {str(e)}")
    elif text_content:
        filename = "pasted_manuscript.txt"
        para_lines = [p.strip() for p in text_content.split("\n\n") if p.strip()]
        paras, sites, references = parse_paragraphs_list(para_lines)
    else:
        raise HTTPException(status_code=400, detail="Must provide either a .docx file or text_content.")

    # Run validation & reachability on all references
    verdicts: Dict[int, ValidationVerdict] = {}
    for ref in references:
        verdicts[ref.ref_num] = validate_single_reference(ref)

    # Map usage and AMA order
    mappings, seq_valid, warnings = map_usage_and_sequence(references, sites)

    total_reachable = sum(1 for v in verdicts.values() if v.is_reachable)
    total_broken = sum(1 for v in verdicts.values() if v.status == "unreachable")
    total_missing = sum(1 for v in verdicts.values() if v.status == "missing_doi")

    summary = AuditSummary(
        filename=filename,
        total_citations=len(sites),
        total_references=len(references),
        total_reachable=total_reachable,
        total_broken=total_broken,
        total_missing_doi=total_missing,
        consecutive_order_valid=seq_valid,
        order_warnings=warnings,
        sites=sites,
        references=references,
        verdicts=verdicts,
        mappings=mappings
    )

    JOBS_CACHE[job_id] = {
        "summary": summary,
        "file_bytes": file_bytes,
        "filename": filename,
        "paras": paras,
        "sites": sites,
        "references": references,
        "verdicts": verdicts,
        "mappings": mappings
    }

    return {"job_id": job_id, "summary": summary}

@app.post("/api/link/{job_id}")
async def link_manuscript(job_id: str):
    if job_id not in JOBS_CACHE:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    
    job = JOBS_CACHE[job_id]
    if not job["file_bytes"]:
        raise HTTPException(status_code=400, detail="Linking requires an uploaded .docx file.")

    out_stream = BytesIO()
    link_docx_manuscript(
        docx_input=BytesIO(job["file_bytes"]),
        sites=job["sites"],
        references=job["references"],
        verdicts=job["verdicts"],
        output_target=out_stream
    )
    job["linked_bytes"] = out_stream.getvalue()
    job["ris_text"] = generate_ris(job["references"], job["verdicts"])

    return {
        "job_id": job_id,
        "status": "ready",
        "download_docx": f"/api/download/{job_id}/docx",
        "download_ris": f"/api/download/{job_id}/ris",
        "download_report": f"/api/download/{job_id}/report"
    }

@app.get("/api/download/{job_id}/docx")
def download_docx(job_id: str):
    if job_id not in JOBS_CACHE or "linked_bytes" not in JOBS_CACHE[job_id]:
        raise HTTPException(status_code=404, detail="Linked file not ready.")
    
    orig_name = JOBS_CACHE[job_id]["filename"]
    base = os.path.splitext(orig_name)[0]
    out_name = f"{base}_zotero_linked.docx"
    return Response(
        content=JOBS_CACHE[job_id]["linked_bytes"],
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'}
    )

@app.get("/api/download/{job_id}/ris")
def download_ris(job_id: str):
    if job_id not in JOBS_CACHE:
        raise HTTPException(status_code=404, detail="Job not found.")
    
    job = JOBS_CACHE[job_id]
    ris_content = job.get("ris_text") or generate_ris(job["references"], job["verdicts"])
    base = os.path.splitext(job["filename"])[0]
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
    summary: AuditSummary = job["summary"]

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

    base = os.path.splitext(job["filename"])[0]
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
