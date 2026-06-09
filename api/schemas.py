"""Pydantic schemas for the Parser API request/response models."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class ExtractionRequest(BaseModel):
    """Query parameters accepted by POST /extract."""
    dpi: int = Field(default=200, ge=100, le=600, description="Render DPI (100–600)")
    ocr_backend: str = Field(default="auto", pattern="^(auto|paddle|easyocr)$")
    known_panels: list[str] = Field(default_factory=list,
                                    description="Pre-known panel labels to boost confidence")
    verbose: bool = False


class TokenResult(BaseModel):
    page: int
    tile_id: str
    raw_text: str
    normalized_text: str
    classification: str
    panel: Optional[str]
    circuit: Optional[str]
    confidence: str          # high / medium / low / reject
    confidence_score: float
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    reason: str
    needs_human_review: bool


class ExtractionSummary(BaseModel):
    pdf_name: str
    total_pages: int
    total_tokens: int
    panel_circuit_matches: int
    rejected: int
    needs_human_review: int
    known_panels: list[str]


class ExtractionResponse(BaseModel):
    summary: ExtractionSummary
    panel_circuits: list[TokenResult]
    all_tokens: list[TokenResult]
    excel_download_path: Optional[str] = None
    json_download_path: Optional[str] = None
