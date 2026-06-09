from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, model_validator


class BBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2

    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def iou(self, other: "BBox") -> float:
        ix1 = max(self.x1, other.x1)
        iy1 = max(self.y1, other.y1)
        ix2 = min(self.x2, other.x2)
        iy2 = min(self.y2, other.y2)
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        union = self.area() + other.area() - inter
        return inter / union if union > 0 else 0.0


class OCRToken(BaseModel):
    raw_text: str
    normalized_text: str = ""
    ocr_confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    bbox: BBox
    page: int
    tile_id: str = ""

    @model_validator(mode="after")
    def _default_normalized(self) -> "OCRToken":
        if not self.normalized_text:
            self.normalized_text = self.raw_text
        return self


class PanelCircuitCandidate(BaseModel):
    token: OCRToken
    classification: str = "unknown"
    panel: Optional[str] = None
    circuit: Optional[str] = None   # comma-separated string, e.g. "29,31"
    confidence: str = "reject"      # high / medium / low / reject
    confidence_score: float = 0.0
    geometry_match: bool = False
    known_panel_match: bool = False
    reason: str = ""
    needs_human_review: bool = False

    def to_row(self) -> dict:
        b = self.token.bbox
        return {
            "page": self.token.page,
            "tile_id": self.token.tile_id,
            "raw_text": self.token.raw_text,
            "normalized_text": self.token.normalized_text,
            "classification": self.classification,
            "panel": self.panel or "",
            "circuit": self.circuit or "",
            "confidence": self.confidence,
            "bbox_x1": round(b.x1, 1),
            "bbox_y1": round(b.y1, 1),
            "bbox_x2": round(b.x2, 1),
            "bbox_y2": round(b.y2, 1),
            "reason": self.reason,
            "needs_human_review": self.needs_human_review,
        }


class ExtractionResult(BaseModel):
    pdf_path: str
    total_pages: int
    candidates: list[PanelCircuitCandidate] = Field(default_factory=list)
    known_panels: list[str] = Field(default_factory=list)

    @property
    def panel_circuits(self) -> list[PanelCircuitCandidate]:
        return [c for c in self.candidates if c.classification == "panel_circuit"]

    @property
    def rejected(self) -> list[PanelCircuitCandidate]:
        return [c for c in self.candidates if c.confidence == "reject"]

    @property
    def needs_review(self) -> list[PanelCircuitCandidate]:
        return [c for c in self.candidates if c.needs_human_review]
