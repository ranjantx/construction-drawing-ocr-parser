"""
Circuit continuation joiner — post-classification approach.

Problem
-------
PaddleOCR's DBNet text detector sometimes splits a single annotation like
"UL1-4,8,10,12,14,16,18" into two adjacent OCR boxes:
  box 1: "UL1-4,8,10,12"   → classified as panel_circuit(UL1, 4,8,10,12)
  box 2: "14,16,18"          → classified as multi_circuit(14,16,18)  ← lost!

The same string "EL2-2,4,6,8,10,12,14,20,27,29" might be detected as one box
(no split) so it works fine.

Why not pre-classification text merging?
  Pre-classification merging failed because it merged SEPARATE annotations on
  the same drawing line — e.g. "EL2-13,15,22,24,33,35" + "2,24" (different
  annotation, same Y position but large gap).

Why post-classification is safer
  After classification we know:
  - LEFT  = panel_circuit (has a validated panel + partial circuit list)
  - RIGHT = multi_circuit (pure comma-separated circuit numbers, no panel)
  We only merge these two when the RIGHT fragment is DIRECTLY adjacent to LEFT
  (very small X gap) and is a PURE circuit list (only digits + commas, at least
  one comma).

Safety criteria (ALL must pass)
--------------------------------
1. Left is panel_circuit, Right is multi_circuit.
2. Right raw_text matches exactly  ^[0-9]{1,2}(,[0-9]{1,2})+$
   (at least one comma — rejects standalone numbers like "3" or "14")
3. Same page and same horizontal line (Y-centres within 0.5 × max height).
4. Horizontal gap < TIGHT_GAP_CHARS × average character width of left token.
   Default TIGHT_GAP_CHARS = 1.5 (very tight — only near-touching fragments).
5. Combined circuit list passes all_circuits_valid().
"""

from __future__ import annotations

import logging
import re

from models.data_models import BBox
from pipeline.regex_patterns import all_circuits_valid

logger = logging.getLogger(__name__)

# Only accept fragments that are THIS CLOSE to the preceding panel_circuit token.
# Formula: gap_pixels < TIGHT_GAP_CHARS * avg_char_width_of_panel_circuit_token
# 1.5 means "less than 1.5 character widths away" — nearly touching.
TIGHT_GAP_CHARS: float = 1.5

# Right fragment must ONLY contain digits and commas, with AT LEAST ONE comma.
# This distinguishes "14,16,18" (continuation) from "14" (standalone number).
# Note: real conduit specs always contain non-digit chars (', ", 2R, _DAT etc.)
# so a pure digit+comma fragment is safe to treat as a circuit continuation.
_PURE_CIRCUIT_LIST = re.compile(r"^\d{1,2}(?:,\d{1,2})+$")


def _avg_char_w(token) -> float:
    n = max(1, len(token.raw_text))
    return max(1.0, token.bbox.width / n)


def join_circuit_continuations(candidates: list) -> list:
    """
    Attach orphan circuit-list fragments (multi_circuit) to their nearest
    preceding panel_circuit token.

    Returns a new list with absorbed multi_circuit rows removed.
    Only joins fragments that are DIRECTLY adjacent (near-touching).
    """
    pc_list = [(i, c) for i, c in enumerate(candidates)
               if c.classification == "panel_circuit"]
    mc_list = [(i, c) for i, c in enumerate(candidates)
               if c.classification == "multi_circuit"]

    if not pc_list or not mc_list:
        return candidates

    # Sort fragments LEFT-TO-RIGHT so chain joining works:
    # "UL1-4" → join "8,10,12" → then join "14,16,18" in order.
    # Without sorting, "14,16,18" might be evaluated before "8,10,12"
    # and miss the join because the panel bbox hasn't been extended yet.
    mc_list.sort(key=lambda x: (x[1].token.page, x[1].token.bbox.x1))

    absorbed: set[int] = set()

    for mc_idx, mc in mc_list:
        raw = mc.token.raw_text.strip()

        # Criterion 1: Fragment must be a pure circuit list (digits + commas, with
        # optional leading dash/comma from text split boundaries).
        # Examples:
        #   "14,16,18"      → True (fragment from "UL1-4,8,10,12,14,16,18")
        #   ",14,16,18"     → True (leading comma from OCR split)
        #   "-14,16"        → True (leading dash from text split)
        #   "2,24,33,35"    → True
        #   "E-14"          → False (mixed with letter)
        #   "EL2"           → False (panel label)
        #   "PANEL"         → False (word)
        cleaned = raw.lstrip(',-')  # strip leading dashes/commas
        if not cleaned or not all(c.isdigit() or c == ',' for c in cleaned):
            continue
        if ',' not in cleaned:  # must have at least one comma (is a list, not single number)
            continue

        best_pc_idx: int | None = None
        best_gap: float = float("inf")

        for pc_idx, pc in pc_list:
            if pc_idx in absorbed:
                continue
            if pc.token.page != mc.token.page:
                continue

            # Criterion 2: Same horizontal line
            cy_diff = abs(pc.token.bbox.center_y - mc.token.bbox.center_y)
            h_max   = max(pc.token.bbox.height, mc.token.bbox.height)
            if cy_diff > 0.5 * h_max:
                continue

            # Criterion 3: Fragment must be directly to the RIGHT of panel_circuit
            gap = mc.token.bbox.x1 - pc.token.bbox.x2
            if gap < 0:
                continue   # overlapping — skip (dedup should have handled this)
            threshold = TIGHT_GAP_CHARS * _avg_char_w(pc.token)
            if gap > threshold:
                continue

            if gap < best_gap:
                best_gap    = gap
                best_pc_idx = pc_idx

        if best_pc_idx is None:
            continue

        _, pc = pc_list[best_pc_idx]
        combined = f"{pc.circuit},{cleaned}"  # use cleaned version (no leading punctuation)

        # Criterion 4: Combined list must be valid
        if not all_circuits_valid(combined):
            logger.debug(
                "Fragment join rejected (invalid combined circuits): %s + %s",
                pc.circuit, raw,
            )
            continue

        old_circuit = pc.circuit
        pc.circuit  = combined
        pc.token.bbox = BBox(
            x1=min(pc.token.bbox.x1, mc.token.bbox.x1),
            y1=min(pc.token.bbox.y1, mc.token.bbox.y1),
            x2=max(pc.token.bbox.x2, mc.token.bbox.x2),
            y2=max(pc.token.bbox.y2, mc.token.bbox.y2),
        )
        pc.reason += f" + fragment joined: ...{cleaned}"
        absorbed.add(mc_idx)
        logger.info(
            "Circuit continuation joined: %s [%s] + [%s] -> [%s]  (gap=%.1fpx)",
            pc.panel, old_circuit, raw, combined, best_gap,
        )

    if absorbed:
        logger.info("join_circuit_continuations: %d fragment(s) absorbed", len(absorbed))

    return [c for i, c in enumerate(candidates) if i not in absorbed]
