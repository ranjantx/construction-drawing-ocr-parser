"""
Remove duplicate OCR tokens that arise from overlapping tile regions.
Uses IOU-based greedy NMS: sort by confidence desc, suppress overlapping tokens.
"""

from __future__ import annotations

from config import CFG
from models.data_models import OCRToken


def deduplicate_tokens(
    tokens: list[OCRToken],
    iou_threshold: float = CFG.iou_threshold,
) -> list[OCRToken]:
    """
    Greedy NMS deduplication over OCR tokens.
    Keeps the highest-confidence token when two tokens overlap above iou_threshold.
    Tokens with identical text AND bounding boxes are always collapsed.
    """
    if not tokens:
        return []

    # Sort descending by OCR confidence
    sorted_tokens = sorted(tokens, key=lambda t: t.ocr_confidence, reverse=True)
    kept: list[OCRToken] = []

    for candidate in sorted_tokens:
        suppressed = False
        for existing in kept:
            iou = candidate.bbox.iou(existing.bbox)
            if iou >= iou_threshold:
                suppressed = True
                break
        if not suppressed:
            kept.append(candidate)

    return kept
