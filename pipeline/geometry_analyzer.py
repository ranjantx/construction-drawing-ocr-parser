"""
Geometry-based spatial association of OCR tokens.

Primary use: associate a standalone panel token (e.g. LA1) with a nearby
standalone circuit token (e.g. 1) when they appear as separate OCR results
on different lines.

Association rules:
- circuit is_below panel: same column position ± 1.5× panel width, directly below
- circuit is_right_of panel: same row ± panel height, directly to the right
- proximity: within 3× panel bounding-box height
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from config import CFG
from models.data_models import BBox, OCRToken
from pipeline.regex_patterns import is_circuit_token, is_panel_token

logger = logging.getLogger(__name__)


@dataclass
class GeometryMatch:
    panel_token: OCRToken
    circuit_token: OCRToken
    relation: str  # "below" | "right_of" | "proximity"


def is_below(panel: BBox, circuit: BBox, cfg=CFG) -> bool:
    """True if circuit bbox is directly below panel bbox."""
    if circuit.y1 <= panel.y2:
        return False
    horizontal_ok = abs(circuit.center_x - panel.center_x) <= cfg.horizontal_align_factor * panel.width
    vertical_ok = (circuit.y1 - panel.y2) <= cfg.proximity_factor * panel.height
    return horizontal_ok and vertical_ok


def is_right_of(panel: BBox, circuit: BBox, cfg=CFG) -> bool:
    """True if circuit bbox is directly to the right of panel bbox."""
    if circuit.x1 <= panel.x2:
        return False
    vertical_ok = abs(circuit.center_y - panel.center_y) <= cfg.vertical_align_factor * panel.height
    horizontal_ok = (circuit.x1 - panel.x2) <= cfg.proximity_factor * panel.width
    return vertical_ok and horizontal_ok


def within_proximity(panel: BBox, circuit: BBox, cfg=CFG) -> bool:
    """True if circuit is within proximity_factor × panel height in any direction."""
    max_dist = cfg.proximity_factor * panel.height
    dx = max(0.0, circuit.x1 - panel.x2, panel.x1 - circuit.x2)
    dy = max(0.0, circuit.y1 - panel.y2, panel.y1 - circuit.y2)
    return (dx**2 + dy**2) ** 0.5 <= max_dist


def find_geometry_matches(tokens: list[OCRToken]) -> list[GeometryMatch]:
    """
    Search all token pairs for panel+circuit spatial relationships.
    Returns list of GeometryMatch — caller decides how to merge.
    """
    panel_candidates = [t for t in tokens if is_panel_token(t.normalized_text)]
    circuit_candidates = [t for t in tokens if is_circuit_token(t.normalized_text)]

    matches: list[GeometryMatch] = []
    for panel in panel_candidates:
        for circuit in circuit_candidates:
            if panel.page != circuit.page:
                continue
            pb, cb = panel.bbox, circuit.bbox
            if is_below(pb, cb):
                matches.append(GeometryMatch(panel, circuit, "below"))
            elif is_right_of(pb, cb):
                matches.append(GeometryMatch(panel, circuit, "right_of"))
            elif within_proximity(pb, cb):
                matches.append(GeometryMatch(panel, circuit, "proximity"))

    return matches
