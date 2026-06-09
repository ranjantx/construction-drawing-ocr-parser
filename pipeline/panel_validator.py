"""
Panel schedule discovery using native PDF text layer (no OCR cost).
Searches for schedule keywords, then collects panel tokens nearby.
Returns a set of known panel labels to improve confidence scoring.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from config import CFG
from pipeline.pdf_renderer import get_native_text_blocks
from pipeline.regex_patterns import is_panel_token

logger = logging.getLogger(__name__)


def discover_known_panels(
    pdf_path: str | Path,
    search_radius: float = CFG.panel_schedule_search_radius,
    keywords: tuple = CFG.panel_schedule_keywords,
) -> set[str]:
    """
    Extract known panel labels from panel schedule tables in the PDF.

    Strategy:
    1. Extract native text spans with bounding boxes (fast, no OCR).
    2. Find spans that match schedule keywords.
    3. Collect all PANEL_TOKEN matches within search_radius of those keyword spans.
    Returns empty set if no schedules found (conservative — no false negatives).
    """
    known: set[str] = set()
    try:
        all_blocks = get_native_text_blocks(pdf_path)
    except Exception as exc:
        logger.warning("Failed to extract native text for panel discovery: %s", exc)
        return known

    for page_idx, blocks in all_blocks.items():
        # Find keyword anchor points
        anchors: list[tuple[float, float]] = []
        for block in blocks:
            upper = block["text"].upper()
            if any(kw in upper for kw in keywords):
                bbox = block["bbox"]
                anchors.append(((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2))

        if not anchors:
            continue

        # Collect panel tokens near anchors
        for block in blocks:
            text = block["text"].strip().upper()
            if not is_panel_token(text):
                continue
            bx = (block["bbox"][0] + block["bbox"][2]) / 2
            by = (block["bbox"][1] + block["bbox"][3]) / 2
            for ax, ay in anchors:
                dist = math.hypot(bx - ax, by - ay)
                if dist <= search_radius:
                    known.add(text)
                    logger.debug("Discovered panel from schedule: %s (page %d)", text, page_idx)
                    break

    logger.info("Panel schedule discovery found %d panels: %s", len(known), sorted(known))
    return known
