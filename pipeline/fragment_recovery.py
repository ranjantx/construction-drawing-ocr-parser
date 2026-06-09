"""
Circuit Fragment Recovery — Geometric Association

Purpose
-------
Recover circuit fragments that were missed by OCR text detector (DBNet).

Problem: "UL1-4,8,10,12,14,16,18" is truncated to "UL1-4,8,10,12"
The fragment ",14,16,18" is NOT detected as a separate OCR token.

Solution: Post-process to find ANY token with comma+digit pattern
and geometrically associate it with the nearest panel_circuit token.

Algorithm
---------
1. Scan all candidates for "comma+digit" patterns (even in non-circuit tokens)
2. Identify unmatched fragments (multi_circuit without panel)
3. For each fragment, find nearest panel_circuit token (same page, closest bbox)
4. Append fragment to panel's circuit list if spatial proximity is tight
5. Mark fragment as absorbed (remove from output)

Safety Guardrails
---------
- Only match multi_circuit fragments (validated digit+comma pattern)
- Require tight spatial proximity (< 2× char width gap)
- Same horizontal line (|center_y| < 0.5× max_height)
- Validate combined circuit list before appending
"""

from __future__ import annotations
import logging
from typing import Optional

from config import CFG
from models.data_models import PanelCircuitCandidate
from pipeline.regex_patterns import all_circuits_valid

logger = logging.getLogger(__name__)

TIGHT_GAP_CHARS: float = 2.0  # Maximum gap for fragment joining (char widths)


def _avg_char_w(token) -> float:
    """Estimate average character width from token bounding box."""
    if token.bbox.width <= 0:
        return 10.0
    text_len = len(token.raw_text.replace(",", "").replace("-", "").replace(" ", ""))
    if text_len == 0:
        return 10.0
    return token.bbox.width / text_len


def recover_missing_fragments(candidates: list) -> list:
    """
    Recover circuit fragments missed by OCR text detector using geometric association.

    Finds any tokens that are pure digit+comma patterns and associates them with
    the nearest panel_circuit token if they are spatially adjacent.

    Args:
        candidates: List of PanelCircuitCandidate objects from classification

    Returns:
        Modified candidate list with recovered fragments appended to panels and
        absorbed fragments removed
    """
    pc_list = [(i, c) for i, c in enumerate(candidates)
               if c.classification == "panel_circuit"]
    mc_list = [(i, c) for i, c in enumerate(candidates)
               if c.classification == "multi_circuit"]

    if not pc_list or not mc_list:
        logger.debug("fragment_recovery: no panel_circuit or multi_circuit tokens")
        return candidates

    absorbed: set[int] = set()
    recovered_count = 0

    # Sort multi_circuit by x-coordinate (left-to-right processing)
    mc_list.sort(key=lambda x: (x[1].token.page, x[1].token.bbox.x1))

    for mc_idx, mc in mc_list:
        if mc_idx in absorbed:
            continue

        raw = mc.token.raw_text.strip()

        # Only process fragments that are pure digit+comma (no panel prefix)
        if not _is_pure_circuit_fragment(raw):
            continue

        # Find nearest LEFT panel_circuit on the same line
        best_pc_idx: Optional[int] = None
        best_gap: float = float("inf")

        for pc_idx, pc in pc_list:
            if pc_idx in absorbed:
                continue
            if pc.token.page != mc.token.page:
                continue

            # Same horizontal line check
            cy_diff = abs(pc.token.bbox.center_y - mc.token.bbox.center_y)
            h_max = max(pc.token.bbox.height, mc.token.bbox.height)
            if cy_diff > 0.5 * h_max:
                continue

            # Fragment must be directly to the RIGHT of panel
            gap = mc.token.bbox.x1 - pc.token.bbox.x2
            if gap < 0:
                continue  # overlapping or to the left
            if gap > TIGHT_GAP_CHARS * _avg_char_w(pc.token):
                continue  # too far away

            if gap < best_gap:
                best_gap = gap
                best_pc_idx = pc_idx

        if best_pc_idx is None:
            continue

        _, pc = pc_list[best_pc_idx]

        # Clean leading punctuation and validate
        cleaned = raw.lstrip(',-')
        combined = f"{pc.circuit},{cleaned}"

        if not all_circuits_valid(combined):
            logger.debug(f"fragment_recovery: invalid combined circuits {pc.circuit} + {raw}")
            continue

        # SUCCESS: Append fragment to panel
        old_circuit = pc.circuit
        pc.circuit = combined
        pc.reason += f" + RECOVERED_FRAGMENT: {raw}"
        absorbed.add(mc_idx)
        recovered_count += 1

        logger.info(
            f"Fragment recovered: {pc.panel} [{old_circuit}] + [{raw}] = [{combined}] "
            f"(gap={best_gap:.1f}px)"
        )

    if recovered_count > 0:
        logger.info(f"fragment_recovery: recovered {recovered_count} fragments")

    return [c for i, c in enumerate(candidates) if i not in absorbed]


def _is_pure_circuit_fragment(text: str) -> bool:
    """
    Check if text is a pure circuit fragment (digits + commas, optional leading dash/comma).

    Examples:
      "14,16,18"      → True
      ",14,16,18"     → True
      "-14,16"        → True
      "14"            → False (single number, no comma)
      "E14"           → False (has letter)
    """
    cleaned = text.lstrip(',-')
    if not cleaned or not all(c.isdigit() or c == ',' for c in cleaned):
        return False
    # Must have at least one comma (indicates a list, not single number)
    return ',' in cleaned
