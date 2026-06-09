"""
PDF → high-resolution PIL images.
Uses PyMuPDF (fitz) at configurable DPI.
Optionally masks the title block (bottom ~8% of page) to reduce false positives.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from config import CFG

logger = logging.getLogger(__name__)

# Fraction of page height from bottom to treat as title block
_TITLE_BLOCK_FRACTION = 0.08


def render_page(
    doc: fitz.Document,
    page_index: int,
    dpi: int = CFG.dpi,
) -> np.ndarray:
    """Render a single PDF page to a uint8 RGB numpy array."""
    page = doc[page_index]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return arr.copy()


def mask_title_block(img: np.ndarray) -> np.ndarray:
    """
    Whites out the bottom fraction of the image (typical title block location).
    Returns a copy — does not mutate the input.
    """
    out = img.copy()
    h = out.shape[0]
    cutoff = int(h * (1.0 - _TITLE_BLOCK_FRACTION))
    out[cutoff:, :, :] = 255
    return out


def iter_pages(
    pdf_path: str | Path,
    dpi: int = CFG.dpi,
    mask_title: bool = True,
) -> Iterator[tuple[int, np.ndarray]]:
    """
    Yields (page_index, image_array) for every page in the PDF.
    page_index is 0-based.
    """
    dpi = max(CFG.dpi_min, min(CFG.dpi_max, dpi))
    doc = fitz.open(str(pdf_path))
    try:
        for i in range(len(doc)):
            img = render_page(doc, i, dpi=dpi)
            if mask_title:
                img = mask_title_block(img)
            logger.debug("Rendered page %d at %d DPI — shape %s", i, dpi, img.shape)
            yield i, img
    finally:
        doc.close()


def get_native_text_blocks(
    pdf_path: str | Path,
) -> dict[int, list[dict]]:
    """
    Extract native PDF text blocks (no OCR) for panel schedule discovery.
    Returns {page_index: [{"text": ..., "bbox": (x0,y0,x1,y1)}, ...]}.
    """
    doc = fitz.open(str(pdf_path))
    result: dict[int, list[dict]] = {}
    try:
        for i, page in enumerate(doc):
            blocks = []
            raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            for block in raw.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if text:
                            bbox = span.get("bbox", (0, 0, 0, 0))
                            blocks.append({"text": text, "bbox": bbox})
            result[i] = blocks
    finally:
        doc.close()
    return result
