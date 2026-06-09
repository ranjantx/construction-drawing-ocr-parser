"""
Confidence scoring for PanelCircuitCandidate results.

Three scoring modes
───────────────────
A) Panel schedule available (known_panels not empty):
   score = 0.35×regex + 0.25×known_panel + 0.20×ocr_conf + 0.10×geometry + 0.10×pattern

B) No panel schedule — layout drawing (the common case):
   The 0.25 known_panel weight is redistributed; pattern quality fills the gap:
   score = 0.45×regex + 0.30×ocr_conf + 0.15×geometry + 0.10×pattern

C) Pattern quality boost:
   pattern_score comes from PanelPatternRecognizer which learns the dominant
   panel naming convention (e.g. "LN" = letter+digit pairs) from this drawing
   and scores each label 0.0–1.0 against that convention.
   This rejects oddities like "E201B" (low pattern score) while boosting
   conventional labels like "EL1", "UL2" (pattern score = 1.0).

   Example — mode B, EL1-5, ocr=0.90, pattern=1.0, no geometry:
     score = 0.45 + 0.27 + 0.0 + 0.10 = 0.82  →  MEDIUM

Thresholds (unchanged):
  HIGH   >= 0.85
  MEDIUM >= 0.60
  LOW    >= 0.40
  REJECT  < 0.40

Hard rejects always override the numeric score.
"""

from __future__ import annotations
import logging
from typing import Optional

from config import CFG
from models.data_models import PanelCircuitCandidate
from pipeline.regex_patterns import all_circuits_valid, is_panel_token

logger = logging.getLogger(__name__)


def score_candidate(
    candidate: PanelCircuitCandidate,
    known_panels: set[str],
    panel_recognizer=None,   # Optional[PanelPatternRecognizer]
) -> PanelCircuitCandidate:
    c = candidate

    # ── Hard reject conditions ────────────────────────────────────────────
    if c.classification != "panel_circuit":
        c.confidence = "reject"
        c.confidence_score = 0.0
        c.needs_human_review = False
        return c

    if not c.panel or not c.circuit:
        c.confidence = "reject"
        c.reason += " | Missing panel or circuit"
        return c

    if not is_panel_token(c.panel):
        c.confidence = "reject"
        c.reason += f" | Invalid panel token: {c.panel}"
        return c

    if not all_circuits_valid(c.circuit):
        c.confidence = "reject"
        c.reason += f" | Invalid circuit(s): {c.circuit}"
        return c

    # ── Scoring ───────────────────────────────────────────────────────────
    regex_score = 1.0   # already confirmed by classifier
    ocr_score   = c.token.ocr_confidence
    geo_score   = 0.8 if c.geometry_match else 0.0

    known_panel_score = 1.0 if (known_panels and c.panel in known_panels) else 0.0
    c.known_panel_match = known_panel_score > 0

    # Pattern quality score — how well does this panel label fit the dominant
    # naming convention discovered by PanelPatternRecognizer?
    # 1.0 = matches dominant template (e.g. EL1 in an EL*/UL* drawing)
    # 0.5 = doesn't match dominant template (possible OCR noise or unusual panel like E201B)
    # 0.0 = failed hard pre-filter (spaces, word, too long)
    if panel_recognizer is not None and c.panel:
        pattern_score = panel_recognizer.score_label(c.panel)

        # Debug: log E201B specifically
        if c.panel == "E201B":
            ocr_conf = c.token.ocr_confidence if hasattr(c.token, 'ocr_confidence') else 0.0
            logger.info(
                f"DEBUG E201B: pattern_score={pattern_score}, known_panel={known_panel_score}, ocr_conf={ocr_conf}"
            )

        # CRITICAL: Reject outlier panels (pattern_score=0.0) or unusual panels (0.5)
        # unless they're in the known_panels list
        if pattern_score == 0.0:
            c.confidence = "reject"
            c.reason += " | Panel failed hard pre-filter (invalid structure)"
            return c
        if pattern_score == 0.5 and not known_panel_score:
            # Outlier panel (doesn't match dominant template) AND not in known_panels
            # Reject unless OCR confidence is exceptionally high (>0.95)
            ocr_conf = c.token.ocr_confidence if hasattr(c.token, 'ocr_confidence') else 0.0
            logger.info(f"DEBUG E201B guard check: pattern={pattern_score}, known_panel={known_panel_score}, ocr={ocr_conf:.4f}, threshold=0.95, reject={ocr_conf < 0.95}")
            if ocr_conf < 0.95:
                c.confidence = "reject"
                c.reason += f" | Outlier panel '{c.panel}' (pattern={pattern_score}, ocr={ocr_conf:.3f})"
                logger.info(f"DEBUG E201B REJECTED: {c.reason}")
                return c
    else:
        pattern_score = 0.7   # neutral when no recognizer available

    if known_panels:
        # Mode A — panel schedule available
        total = (
            0.35 * regex_score
            + 0.25 * known_panel_score
            + 0.20 * ocr_score
            + 0.10 * geo_score
            + 0.10 * pattern_score
        )
    else:
        # Mode B — no panel schedule (layout drawing)
        # Redistribute the 0.25 known_panel weight; pattern fills the gap.
        total = (
            0.45 * regex_score
            + 0.30 * ocr_score
            + 0.15 * geo_score
            + 0.10 * pattern_score
        )

    c.confidence_score = round(total, 4)

    if total >= CFG.conf_high:
        c.confidence = "high"
    elif total >= CFG.conf_medium:
        c.confidence = "medium"
    elif total >= CFG.conf_low:
        c.confidence = "low"
    else:
        c.confidence = "reject"

    # ── Change 3: human review flag — only flag truly uncertain cases ─────
    # Do NOT flag MEDIUM-confidence regex matches with acceptable OCR.
    c.needs_human_review = (
        c.confidence == "low"
        or c.token.ocr_confidence < CFG.ocr_conf_review_threshold
        or c.geometry_match    # geometry-only associations are less reliable
        # REMOVED: c.confidence == "medium" — was flagging all valid results
    )

    return c


def score_all(
    candidates: list[PanelCircuitCandidate],
    known_panels: set[str],
    panel_recognizer=None,
) -> list[PanelCircuitCandidate]:
    return [score_candidate(c, known_panels, panel_recognizer) for c in candidates]
