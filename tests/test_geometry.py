"""Unit tests for geometry-based spatial association."""

import pytest
from models.data_models import BBox, OCRToken
from pipeline.geometry_analyzer import find_geometry_matches, is_below, is_right_of, within_proximity
from config import CFG


def _bbox(x1, y1, x2, y2) -> BBox:
    return BBox(x1=x1, y1=y1, x2=x2, y2=y2)


def _token(text: str, bbox: BBox, page: int = 0) -> OCRToken:
    return OCRToken(
        raw_text=text, normalized_text=text,
        ocr_confidence=0.95, bbox=bbox, page=page,
    )


# ---------------------------------------------------------------------------
# is_below
# ---------------------------------------------------------------------------

class TestIsBelow:
    def test_directly_below_same_column(self):
        panel = _bbox(100, 100, 150, 120)   # center_x=125, height=20, width=50
        circuit = _bbox(110, 125, 140, 145) # directly below, within 1.5× width
        assert is_below(panel, circuit)

    def test_too_far_below(self):
        panel = _bbox(100, 100, 150, 120)  # height=20
        # More than 3× height (60px) below
        circuit = _bbox(110, 190, 140, 210)
        assert not is_below(panel, circuit)

    def test_horizontally_misaligned(self):
        panel = _bbox(100, 100, 150, 120)   # center_x=125, width=50
        # circuit center_x = 300, far right — outside 1.5×50=75 tolerance
        circuit = _bbox(275, 125, 325, 145)
        assert not is_below(panel, circuit)

    def test_circuit_above_panel(self):
        panel = _bbox(100, 100, 150, 120)
        circuit = _bbox(110, 70, 140, 90)  # above panel
        assert not is_below(panel, circuit)


# ---------------------------------------------------------------------------
# is_right_of
# ---------------------------------------------------------------------------

class TestIsRightOf:
    def test_directly_right_same_row(self):
        panel = _bbox(100, 100, 150, 120)   # center_y=110, height=20
        circuit = _bbox(160, 105, 190, 125) # right of panel, within height tolerance
        assert is_right_of(panel, circuit)

    def test_too_far_right(self):
        panel = _bbox(100, 100, 150, 120)  # width=50
        # More than 3× width (150px) to the right
        circuit = _bbox(320, 105, 350, 125)
        assert not is_right_of(panel, circuit)

    def test_vertically_misaligned(self):
        panel = _bbox(100, 100, 150, 120)   # center_y=110, height=20
        # circuit center_y = 200, far below — outside 1.0×20=20 tolerance
        circuit = _bbox(160, 190, 190, 210)
        assert not is_right_of(panel, circuit)


# ---------------------------------------------------------------------------
# within_proximity
# ---------------------------------------------------------------------------

class TestWithinProximity:
    def test_close_token(self):
        panel = _bbox(100, 100, 150, 120)   # height=20, proximity=3×20=60
        circuit = _bbox(120, 140, 145, 155) # 20px below, within 60
        assert within_proximity(panel, circuit)

    def test_far_token(self):
        panel = _bbox(100, 100, 150, 120)
        circuit = _bbox(300, 300, 340, 315)
        assert not within_proximity(panel, circuit)


# ---------------------------------------------------------------------------
# find_geometry_matches — LA1 + 1 pairing simulation
# ---------------------------------------------------------------------------

class TestFindGeometryMatches:
    def test_la1_below_1(self):
        """LA1 on one line, circuit 1 directly below — should produce a match."""
        la1 = _token("LA1", _bbox(200, 100, 240, 120))
        one = _token("1",   _bbox(215, 125, 225, 140))  # directly below LA1
        matches = find_geometry_matches([la1, one])
        assert len(matches) == 1
        assert matches[0].panel_token.normalized_text == "LA1"
        assert matches[0].circuit_token.normalized_text == "1"
        assert matches[0].relation in ("below", "right_of", "proximity")

    def test_no_match_far_apart(self):
        la1 = _token("LA1", _bbox(200, 100, 240, 120))
        two = _token("2",   _bbox(500, 500, 515, 520))  # far away
        matches = find_geometry_matches([la1, two])
        assert len(matches) == 0

    def test_different_pages_no_match(self):
        la1 = _token("LA1", _bbox(200, 100, 240, 120))
        la1_pg1 = OCRToken(raw_text="LA1", normalized_text="LA1", ocr_confidence=0.9,
                           bbox=_bbox(200, 100, 240, 120), page=0)
        circ_pg2 = OCRToken(raw_text="5", normalized_text="5", ocr_confidence=0.9,
                            bbox=_bbox(215, 125, 225, 140), page=1)
        matches = find_geometry_matches([la1_pg1, circ_pg2])
        assert len(matches) == 0
