"""Parser FastAPI service — wraps the CLI pipeline for HTTP access.

Endpoints
─────────
POST /extract          Upload PDF → synchronous JSON response
POST /extract/async    Upload PDF → job_id; poll GET /extract/status/{job_id}
GET  /extract/status/{job_id}
GET  /extract/download/{job_id}/{filename}   Download Excel or JSON
GET  /health
GET  /docs             Swagger UI
"""
from __future__ import annotations

import logging
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# Ensure the parser package root is on sys.path when running as a sub-package
_PARSER_ROOT = Path(__file__).resolve().parents[1]
if str(_PARSER_ROOT) not in sys.path:
    sys.path.insert(0, str(_PARSER_ROOT))

from api.schemas import ExtractionResponse, ExtractionSummary, TokenResult

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S", level=logging.INFO,
)
logger = logging.getLogger(__name__)

_jobs: dict[str, dict] = {}
OUTPUT_ROOT = Path("output/api")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AECInspire Parser API",
    description=(
        "Extracts electrical panel labels and circuit numbers from PDF construction drawings.\n\n"
        "**Pipeline**: PDF → 30% overlapping tiles → OCR → 9-step classifier → "
        "geometry association → NEC validation → confidence scoring → JSON + Excel output."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Core extraction ───────────────────────────────────────────────────────────

def _run_extraction(
    pdf_bytes: bytes,
    pdf_name: str,
    dpi: int,
    ocr_backend: str,
    known_panels: list[str],
    output_dir: Path,
) -> ExtractionResponse:
    """Write PDF to a temp file, run the parser pipeline, return structured response."""
    from config import CFG
    from extract_circuits import run_pipeline
    from models.data_models import ExtractionResult
    from pipeline.classifier import classify_all
    from pipeline.confidence_scorer import score_all
    from pipeline.coordinate_mapper import make_ocr_token
    from pipeline.deduplicator import deduplicate_tokens
    from pipeline.geometry_analyzer import find_geometry_matches
    from pipeline.normalizer import normalize_text
    from pipeline.ocr_engine import run_ocr_on_tile, set_backend, get_requested_backend
    from pipeline.output_writer import write_outputs
    from pipeline.panel_validator import discover_known_panels
    from pipeline.pdf_renderer import iter_pages
    from pipeline.preprocessor import preprocess_tile
    from pipeline.regex_patterns import looks_like_panel_label
    from pipeline.tiler import tile_image

    # Write bytes to temp PDF
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = Path(tmp.name)

    try:
        set_backend(ocr_backend)
        active_backend = get_requested_backend()

        known_panels_set = discover_known_panels(str(tmp_path))
        known_panels_set |= {p.upper() for p in known_panels}

        all_tokens = []
        page_count = 0

        for page_idx, page_img in iter_pages(str(tmp_path), dpi=dpi, mask_title=True):
            page_count += 1
            preprocess_backend = "paddle" if active_backend == "paddle" else "easyocr"
            page_tokens = []

            for tile in tile_image(page_img, page_index=page_idx):
                processed = preprocess_tile(tile.image, backend=preprocess_backend)
                for ocr_result in run_ocr_on_tile(processed):
                    token = make_ocr_token(tile, ocr_result)
                    token.normalized_text = normalize_text(token.raw_text, known_panels_set)
                    page_tokens.append(token)

            page_tokens = deduplicate_tokens(page_tokens)
            all_tokens.extend(page_tokens)

        candidates = classify_all(all_tokens, known_panels=known_panels_set)

        geo_matches = find_geometry_matches(all_tokens)
        geo_token_ids = {}
        for match in geo_matches:
            panel_text = match.panel_token.normalized_text
            if not looks_like_panel_label(panel_text, known_panels_set):
                continue
            geo_token_ids[id(match.panel_token)] = match

        for candidate in candidates:
            tok_id = id(candidate.token)
            if tok_id in geo_token_ids:
                match = geo_token_ids[tok_id]
                candidate.classification = "panel_circuit"
                candidate.panel = match.panel_token.normalized_text
                candidate.circuit = match.circuit_token.normalized_text
                candidate.geometry_match = True
                candidate.reason = f"Geometry ({match.relation}): {candidate.panel}-{candidate.circuit}"

        candidates = score_all(candidates, known_panels_set)

        result_obj = ExtractionResult(
            pdf_path=str(tmp_path),
            total_pages=page_count,
            candidates=candidates,
            known_panels=sorted(known_panels_set),
        )
        write_outputs(result_obj, str(output_dir))

    finally:
        tmp_path.unlink(missing_ok=True)

    # Build API response from candidates
    def _to_token(c) -> TokenResult:
        b = c.token.bbox
        return TokenResult(
            page=c.token.page,
            tile_id=c.token.tile_id,
            raw_text=c.token.raw_text,
            normalized_text=c.token.normalized_text,
            classification=c.classification,
            panel=c.panel or None,
            circuit=c.circuit or None,
            confidence=c.confidence,
            confidence_score=float(c.confidence_score),
            bbox_x1=float(b.x1), bbox_y1=float(b.y1),
            bbox_x2=float(b.x2), bbox_y2=float(b.y2),
            reason=c.reason,
            needs_human_review=c.needs_human_review,
        )

    all_token_results = [_to_token(c) for c in candidates]
    panel_circuits    = [t for t in all_token_results if t.classification == "panel_circuit"]

    # Find output files
    excel_files = sorted(output_dir.glob("circuits*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    json_files  = sorted(output_dir.glob("circuits*.json"),  key=lambda p: p.stat().st_mtime, reverse=True)

    return ExtractionResponse(
        summary=ExtractionSummary(
            pdf_name=pdf_name,
            total_pages=result_obj.total_pages,
            total_tokens=len(all_token_results),
            panel_circuit_matches=len(panel_circuits),
            rejected=sum(1 for t in all_token_results if t.confidence == "reject"),
            needs_human_review=sum(1 for t in all_token_results if t.needs_human_review),
            known_panels=result_obj.known_panels,
        ),
        panel_circuits=panel_circuits,
        all_tokens=all_token_results,
        excel_download_path=(
            f"/extract/download/{output_dir.name}/{excel_files[0].name}"
            if excel_files else None
        ),
        json_download_path=(
            f"/extract/download/{output_dir.name}/{json_files[0].name}"
            if json_files else None
        ),
    )


# ── Synchronous endpoint ──────────────────────────────────────────────────────

@app.post(
    "/extract",
    response_model=ExtractionResponse,
    summary="Extract panel/circuit labels (synchronous)",
)
async def extract_sync(
    file: UploadFile = File(..., description="PDF drawing file"),
    dpi: int = Form(200, ge=100, le=600, description="Render DPI (200 recommended for E-size)"),
    ocr_backend: str = Form("auto", description="auto | paddle | easyocr"),
    known_panels: str = Form("", description="Comma-separated panel labels, e.g. L1,LB1,7LA"),
):
    """
    Upload a PDF and receive panel/circuit extraction results synchronously.

    - Returns `panel_circuits` list (high/medium/low confidence matches).
    - Returns `all_tokens` list (every OCR detection with classification).
    - Tokens with `needs_human_review=true` are ambiguous or low-confidence.
    - Download Excel via the `excel_download_path` URL in the response.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    pdf_bytes = await file.read()
    panels = [p.strip().upper() for p in known_panels.split(",") if p.strip()]
    job_id  = uuid.uuid4().hex[:12]
    out_dir = OUTPUT_ROOT / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        return _run_extraction(pdf_bytes, file.filename, dpi, ocr_backend, panels, out_dir)
    except Exception as exc:
        logger.exception("Synchronous extraction failed")
        raise HTTPException(500, f"Extraction error: {exc}")


# ── Asynchronous endpoint ─────────────────────────────────────────────────────

@app.post("/extract/async", summary="Extract panel/circuit labels (async — returns job_id)")
async def extract_async(
    file: UploadFile = File(...),
    dpi: int = Form(200, ge=100, le=600),
    ocr_backend: str = Form("auto"),
    known_panels: str = Form(""),
):
    """
    Upload a PDF and get a job_id immediately.
    Poll `GET /extract/status/{job_id}` until `status == "complete"`.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    pdf_bytes = await file.read()
    panels    = [p.strip().upper() for p in known_panels.split(",") if p.strip()]
    job_id    = uuid.uuid4().hex[:12]
    out_dir   = OUTPUT_ROOT / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    _jobs[job_id] = {"status": "queued", "pdf_name": file.filename}

    def _worker():
        _jobs[job_id]["status"] = "running"
        try:
            result = _run_extraction(pdf_bytes, file.filename, dpi, ocr_backend, panels, out_dir)
            _jobs[job_id].update({"status": "complete", "result": result.model_dump()})
        except Exception as exc:
            logger.exception("Async extraction failed: job=%s", job_id)
            _jobs[job_id].update({"status": "failed", "error": str(exc)})

    threading.Thread(target=_worker, daemon=True).start()
    return {"job_id": job_id, "status": "queued", "poll_url": f"/extract/status/{job_id}"}


@app.get("/extract/status/{job_id}", summary="Poll async job status")
async def extract_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return job


# ── File download ─────────────────────────────────────────────────────────────

@app.get("/extract/download/{job_id}/{filename}", summary="Download Excel or JSON output file")
async def download_output(job_id: str, filename: str):
    fp = OUTPUT_ROOT / job_id / filename
    if not fp.exists():
        raise HTTPException(404, "File not found")
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
            if filename.endswith(".xlsx") else "application/json"
    return FileResponse(path=str(fp), filename=filename, media_type=media)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "parser-api", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8001, reload=False)
