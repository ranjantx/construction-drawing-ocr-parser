"""
Drawing Zone Masker.

Purpose
-------
Engineering drawing PDFs contain multiple distinct zones:
  ┌────────────────────────────────────────────────────────┐
  │  REV BLOCK                                             │
  │  (upper-right)                                         │
  ├──────────────────────────────────────┬─────────────────┤
  │                                      │  NOTES /        │
  │      DRAWING AREA                    │  GENERAL NOTES  │
  │   (electrical symbols, annotations,  │  (dense text    │
  │    panel labels, circuit numbers)    │   paragraphs)   │
  │                                      │                 │
  ├──────────────────────────────────────┴─────────────────┤
  │              TITLE BLOCK (company, project, sheet)     │
  └────────────────────────────────────────────────────────┘

Running OCR on the title block, notes, and revision areas produces noise
tokens (dates, company names, spec paragraphs) that pollute the panel-circuit
classifier and slow down processing.

This module identifies those zones from the PDF's native text layer
(no OCR cost) and returns pixel-level masks to white-out those regions
before tiling.

Detection strategy
------------------
1. Title block   — bottom TITLE_BLOCK_PCT% of page (fixed default + keyword confirm)
2. Notes/specs   — text-dense blocks (word density > NOTES_DENSITY_THRESHOLD)
3. Keyword zones — blocks containing ZONE_KEYWORDS (NOTES, LEGEND, REVISION…)
4. Border strip  — thin strip around page edge (rarely contains drawings)

All zones are returned as (x1, y1, x2, y2) in PDF points.
The caller converts to pixel coordinates at the current DPI.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import numpy as np

logger = logging.getLogger(__name__)

# ── Tunable constants ──────────────────────────────────────────────────────
# Bottom fraction of page always treated as title block
TITLE_BLOCK_PCT: float = 0.10

# Word density (words per 1000 pt²) above which a block is considered "notes"
NOTES_DENSITY_THRESHOLD: float = 0.05

# Border strip width in PDF points (1 pt = 1/72 inch)
BORDER_STRIP_PT: float = 18.0     # ≈ 0.25 inch

# Keywords that identify a zone as non-drawing
ZONE_KEYWORDS: frozenset[str] = frozenset({
    "GENERAL NOTE", "NOTES:", "NOTE:", "LEGEND", "SYMBOL",
    "REVISION", "REVISIONS", "SHEET NO", "DRAWING NO",
    "DRAWN BY", "CHECKED BY", "APPROVED BY", "PROJECT NO",
    "DATE:", "SCALE:", "SPECIFICATION", "SPECIFICATIONS",
    "SEE SPECS", "SEE DETAIL", "REFER TO",
    "CONTRACTOR", "ENGINEER", "ARCHITECT",
    "COPYRIGHT", "CONFIDENTIAL",
})

# Minimum block area (pt²) to consider for density analysis
MIN_BLOCK_AREA_PT2: float = 2000.0
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class MaskedZone:
    """A rectangular region (PDF points) to exclude from OCR."""
    x1: float
    y1: float
    x2: float
    y2: float
    reason: str

    def to_pixel_bbox(self, dpi: float) -> tuple[int, int, int, int]:
        """Convert PDF-point bbox to pixel coordinates at given DPI."""
        scale = dpi / 72.0
        return (
            int(self.x1 * scale),
            int(self.y1 * scale),
            int(self.x2 * scale),
            int(self.y2 * scale),
        )


@dataclass
class DrawingZones:
    """Collection of masked zones for one PDF page."""
    page_width_pt:  float
    page_height_pt: float
    zones: list[MaskedZone] = field(default_factory=list)

    def apply_to_image(self, img: np.ndarray, dpi: float) -> np.ndarray:
        """
        White-out all masked zones in the given page image.
        Returns a copy; does not mutate the input.
        """
        out = img.copy()
        for zone in self.zones:
            px1, py1, px2, py2 = zone.to_pixel_bbox(dpi)
            # Clamp to image bounds
            h, w = out.shape[:2]
            px1 = max(0, min(px1, w))
            py1 = max(0, min(py1, h))
            px2 = max(0, min(px2, w))
            py2 = max(0, min(py2, h))
            if px2 > px1 and py2 > py1:
                out[py1:py2, px1:px2] = 255
        return out

    def coverage_fraction(self) -> float:
        """Fraction of page area covered by masked zones."""
        page_area = self.page_width_pt * self.page_height_pt
        if page_area <= 0:
            return 0.0
        masked = sum((z.x2 - z.x1) * (z.y2 - z.y1) for z in self.zones)
        return min(1.0, masked / page_area)


def detect_zones(
    pdf_path: str | Path,
    page_index: int = 0,
    title_block_pct: float = TITLE_BLOCK_PCT,
) -> DrawingZones:
    """
    Analyse a single PDF page and return DrawingZones describing all
    non-drawing regions that should be excluded from OCR.

    Uses only the native PDF text layer — zero OCR cost.
    """
    doc   = fitz.open(str(pdf_path))
    page  = doc[page_index]
    pw    = page.rect.width
    ph    = page.rect.height
    zones = DrawingZones(page_width_pt=pw, page_height_pt=ph)

    # ── Zone 1: Title block (fixed bottom strip) ──────────────────────────
    tb_y1 = ph * (1.0 - title_block_pct)
    zones.zones.append(MaskedZone(0, tb_y1, pw, ph, "title_block_fixed"))

    # ── Zone 2: Border strip (thin margin around page edges) ──────────────
    zones.zones.append(MaskedZone(0, 0, BORDER_STRIP_PT, ph, "border_left"))
    zones.zones.append(MaskedZone(0, 0, pw, BORDER_STRIP_PT, "border_top"))
    zones.zones.append(MaskedZone(pw - BORDER_STRIP_PT, 0, pw, ph, "border_right"))

    # ── Zone 3: Keyword-based and density-based zones ─────────────────────
    raw_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    keyword_blocks: list[MaskedZone] = []
    dense_blocks:   list[MaskedZone] = []

    for block in raw_blocks.get("blocks", []):
        if block.get("type") != 0:   # type 0 = text
            continue

        bx1, by1, bx2, by2 = block.get("bbox", (0, 0, 0, 0))
        bw = bx2 - bx1
        bh = by2 - by1
        area = bw * bh

        # Collect all text in this block
        block_text = " ".join(
            span.get("text", "")
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        ).strip().upper()

        if not block_text:
            continue

        # Zone 3a: keyword match
        for kw in ZONE_KEYWORDS:
            if kw in block_text:
                # Expand the block outward by 20% to capture surrounding content
                expand_x = bw * 0.20
                expand_y = bh * 0.50
                zone = MaskedZone(
                    max(0, bx1 - expand_x), max(0, by1 - expand_y),
                    min(pw, bx2 + expand_x), min(ph, by2 + expand_y),
                    f"keyword:{kw}",
                )
                keyword_blocks.append(zone)
                logger.debug("Zone keyword %r found at (%.0f,%.0f,%.0f,%.0f)",
                             kw, bx1, by1, bx2, by2)
                break

        # Zone 3b: text density (notes paragraphs)
        if area >= MIN_BLOCK_AREA_PT2:
            word_count  = len(block_text.split())
            density     = word_count / (area / 1000.0)
            if density > NOTES_DENSITY_THRESHOLD:
                zone = MaskedZone(
                    max(0, bx1 - 5), max(0, by1 - 5),
                    min(pw, bx2 + 5), min(ph, by2 + 5),
                    f"dense_text(density={density:.3f})",
                )
                dense_blocks.append(zone)
                logger.debug(
                    "Dense text block density=%.3f  words=%d  area=%.0f  "
                    "preview: %s",
                    density, word_count, area, block_text[:60],
                )

    zones.zones.extend(keyword_blocks)
    zones.zones.extend(dense_blocks)
    doc.close()

    logger.info(
        "Zone detection page %d: %d zones (title=%d, keyword=%d, dense=%d, border=3) "
        "covering %.1f%% of page",
        page_index,
        len(zones.zones),
        1,
        len(keyword_blocks),
        len(dense_blocks),
        zones.coverage_fraction() * 100,
    )
    return zones


def detect_all_zones(
    pdf_path: str | Path,
    title_block_pct: float = TITLE_BLOCK_PCT,
) -> dict[int, DrawingZones]:
    """Detect zones for every page in the PDF. Returns {page_index: DrawingZones}."""
    doc    = fitz.open(str(pdf_path))
    result = {}
    for i in range(len(doc)):
        result[i] = detect_zones(pdf_path, page_index=i,
                                  title_block_pct=title_block_pct)
    doc.close()
    return result
