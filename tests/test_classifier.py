"""Unit tests for the 9-step token classifier."""

import pytest
from models.data_models import BBox, OCRToken
from pipeline.classifier import classify_token


def _make_token(text: str) -> OCRToken:
    return OCRToken(
        raw_text=text,
        normalized_text=text,
        ocr_confidence=0.95,
        bbox=BBox(x1=10, y1=10, x2=100, y2=30),
        page=0,
    )


# ---------------------------------------------------------------------------
# panel_circuit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,panel,circuits", [
    ("L1-5",        "L1",    "5"),
    ("P1-57",       "P1",    "57"),
    ("7LA-29",      "7LA",   "29"),
    ("LB1-35",      "LB1",   "35"),
    ("LL1B-1,3,5",  "LL1B",  "1,3,5"),
    ("LB1-29,31",   "LB1",   "29,31"),
    ("LA1-1",       "LA1",   "1"),
    ("4LF-8",       "4LF",   "8"),
])
def test_classifies_panel_circuit(text, panel, circuits):
    result = classify_token(_make_token(text))
    assert result.classification == "panel_circuit", f"Expected panel_circuit for {text!r}, got {result.classification}"
    assert result.panel == panel
    assert result.circuit == circuits


# ---------------------------------------------------------------------------
# mounting_height
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ['+42"', "+48AFF", "+36'"])
def test_classifies_mounting_height(text):
    result = classify_token(_make_token(text))
    assert result.classification == "mounting_height", f"Expected mounting_height for {text!r}"


# ---------------------------------------------------------------------------
# room_number
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["112", "114", "200", "300"])
def test_classifies_room_number(text):
    result = classify_token(_make_token(text))
    assert result.classification == "room_number", f"Expected room_number for {text!r}"


# ---------------------------------------------------------------------------
# equipment_tag
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["FC-3", "EQ-10", "2D-06", "300F-60", "300F-79"])
def test_classifies_equipment_tag(text):
    result = classify_token(_make_token(text))
    assert result.classification == "equipment_tag", f"Expected equipment_tag for {text!r}, got {result.classification}"


# ---------------------------------------------------------------------------
# fixture_device_tag
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["B R012", "GX6 R012"])
def test_classifies_fixture_device_tag(text):
    result = classify_token(_make_token(text))
    assert result.classification == "fixture_device_tag", f"Expected fixture_device_tag for {text!r}"


# ---------------------------------------------------------------------------
# switch_leg
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["a", "b", "a,b", "7a", "7b", "7c"])
def test_classifies_switch_leg(text):
    result = classify_token(_make_token(text))
    assert result.classification == "switch_leg", f"Expected switch_leg for {text!r}"


# ---------------------------------------------------------------------------
# unknown (standalone tokens needing geometry pass)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["LA1", "LB1", "L1", "P1"])
def test_standalone_panel_is_unknown(text):
    result = classify_token(_make_token(text))
    assert result.classification == "unknown"


@pytest.mark.parametrize("text", ["5", "29", "42", "84"])
def test_standalone_circuit_is_unknown(text):
    result = classify_token(_make_token(text))
    assert result.classification == "unknown"


# ---------------------------------------------------------------------------
# Reject — invalid circuit numbers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["L1-85", "LB1-0", "LA1-47C"])
def test_invalid_circuit_is_unknown(text):
    result = classify_token(_make_token(text))
    # Either unknown (failed validation) or rejected — must NOT be panel_circuit
    assert result.classification != "panel_circuit", f"Should not be panel_circuit: {text!r}"
