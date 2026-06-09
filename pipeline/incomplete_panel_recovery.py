"""
Incomplete Panel Recovery — Re-OCR for Truncated Circuit Lists

Purpose
-------
Detect panels that end with comma/dash (truncation indicator) and re-OCR
adjacent areas to recover missing circuits.

Problem: "UL1-4,8,10,12" is truncated; missing ",14,16,18"

Solution:
1. Detect truncation: raw_text.endswith(',') or raw_text.endswith('-')
2. Expand search region: grow right 300px, down 100px from panel bbox
3. Re-OCR the region with PaddleOCR
4. Validate result matches circuit pattern: r'\\d{1,2}(,\\d{1,2})+'
5. Append valid circuits to panel

Safety:
- Only process actually-truncated panels (low false-positive rate)
- Strict circuit validation (range 1-84, comma-separated)
- Only append if result is pure circuit list (no text prefix)
"""

from __future__ import annotations
import logging
from typing import Optional

from models.data_models import PanelCircuitCandidate
from pipeline.regex_patterns import all_circuits_valid

logger = logging.getLogger(__name__)


def recover_truncated_panels(
    candidates: list,
    ocr_engine,  # OCR engine with __call__(image) method
    pdf_path: str,
    page_images: dict[int, tuple],  # {page_idx: (image_array, original_width, original_height)}
    dpi: int = 300,
) -> list:
    """
    Recover circuits from truncated panels by re-OCR'ing adjacent regions.

    Args:
        candidates: List of extracted candidates
        ocr_engine: Initialized OCR engine (PaddleOCR wrapper)
        pdf_path: Path to PDF (for re-rendering if needed)
        page_images: Dict mapping page index to (image_array, width, height)
        dpi: DPI used for rendering

    Returns:
        Modified candidates list with recovered circuits appended to truncated panels
    """
    # Find all truncated panels
    truncated = [
        c for c in candidates
        if c.classification == "panel_circuit"
        and (c.token.raw_text.endswith(",") or c.token.raw_text.endswith("-"))
    ]

    if not truncated:
        logger.debug("incomplete_panel_recovery: no truncated panels found")
        return candidates

    recovered_count = 0
    px_per_pt = dpi / 72.0  # Convert PDF points to pixels at given DPI

    for panel in truncated:
        if panel.token.page not in page_images:
            logger.debug(f"incomplete_panel_recovery: page {panel.token.page} image not available")
            continue

        page_img, orig_w, orig_h = page_images[panel.token.page]

        # Expand search region: right 300px, down 100px
        search_bbox = _expand_bbox(
            panel.token.bbox,
            px_per_pt=px_per_pt,
            grow_right=300,
            grow_down=100,
            img_width=page_img.shape[1],
            img_height=page_img.shape[0],
        )

        if search_bbox is None:
            continue

        # Extract sub-image
        x1, y1, x2, y2 = search_bbox
        sub_img = page_img[int(y1) : int(y2), int(x1) : int(x2)]

        if sub_img.size == 0:
            continue

        # Re-OCR the region
        try:
            ocr_result = ocr_engine(sub_img)
            if not ocr_result:
                continue
        except Exception as e:
            logger.debug(f"incomplete_panel_recovery: OCR failed for panel {panel.panel}: {e}")
            continue

        # Extract and validate circuits
        extracted_text = _extract_text_from_ocr(ocr_result)
        extracted_text = extracted_text.strip()

        if not extracted_text:
            continue

        # Only accept pure circuit lists (digits + commas, no text prefix)
        if not _is_pure_circuit_list(extracted_text):
            logger.debug(
                f"incomplete_panel_recovery: extracted text not pure circuits: {extracted_text}"
            )
            continue

        # Validate and append
        combined = f"{panel.circuit},{extracted_text}"
        if not all_circuits_valid(combined):
            logger.debug(
                f"incomplete_panel_recovery: invalid combined circuits: {combined}"
            )
            continue

        # SUCCESS: Append to panel
        old_circuit = panel.circuit
        panel.circuit = combined
        panel.reason += f" + RE_OCR_RECOVERED: {extracted_text}"
        recovered_count += 1

        logger.info(
            f"Truncated panel recovered: {panel.panel} [{old_circuit}] → [{combined}]"
        )

    if recovered_count > 0:
        logger.info(f"incomplete_panel_recovery: recovered {recovered_count} truncated panels")

    return candidates


def _expand_bbox(
    bbox,
    px_per_pt: float,
    grow_right: int = 300,
    grow_down: int = 100,
    img_width: int = 0,
    img_height: int = 0,
) -> Optional[tuple]:
    """
    Expand bounding box to search for missing circuits.

    Returns (x1, y1, x2, y2) in pixel coordinates, or None if invalid.
    """
    try:
        x1 = int(bbox.x1 * px_per_pt)
        y1 = int(bbox.y1 * px_per_pt)
        x2 = int(bbox.x2 * px_per_pt)
        y2 = int(bbox.y2 * px_per_pt)

        # Expand right and down
        x2_expanded = min(x2 + grow_right, img_width)
        y2_expanded = min(y2 + grow_down, img_height)

        # Keep x1 the same (search to the right)
        # Keep y1 the same (search down)

        if x1 < 0 or y1 < 0 or x2_expanded <= x1 or y2_expanded <= y1:
            return None

        return (x1, y1, x2_expanded, y2_expanded)
    except (AttributeError, TypeError):
        return None


def _extract_text_from_ocr(ocr_result) -> str:
    """
    Extract text from OCR result.

    Handles both PaddleOCR list-of-tuples format and dict format.
    """
    if not ocr_result:
        return ""

    texts = []
    for item in ocr_result:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            # Format: ([points], (text, confidence))
            text = item[1][0] if isinstance(item[1], (tuple, list)) else item[1]
            texts.append(str(text))
        elif isinstance(item, dict) and "text" in item:
            # Format: {"text": "...", "confidence": ...}
            texts.append(item["text"])

    return " ".join(texts)


def _is_pure_circuit_list(text: str) -> bool:
    """
    Check if text is a pure circuit list (digits + commas only).

    Accepts:
      "14,16,18"      ✓
      "2,24,33,35"    ✓
      "1-5,7,9"       ✓ (range notation)

    Rejects:
      "E-14"          ✗ (has letters)
      "Circuit: 14"   ✗ (has text prefix)
      "14"            ✓ (single circuit, valid but rare in re-OCR)
    """
    # Must be all digits, commas, and dashes (for ranges)
    cleaned = text.replace(",", "").replace("-", "").replace(" ", "")
    return cleaned.isdigit() and len(cleaned) > 0
