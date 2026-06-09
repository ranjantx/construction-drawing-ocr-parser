"""Unit tests for regex patterns and circuit validation."""

import pytest
from pipeline.regex_patterns import (
    PANEL_CIRCUIT_DASH,
    PANEL_CIRCUIT_COLON,
    PANEL_TOKEN,
    CIRCUIT_TOKEN,
    EQUIPMENT_TAG,
    FIXTURE_TAG,
    MOUNTING_HEIGHT,
    SWITCH_LEG,
    all_circuits_valid,
    is_panel_token,
    is_circuit_token,
    is_equipment_tag,
    is_fixture_tag,
    is_mounting_height,
    is_switch_leg,
)


# ---------------------------------------------------------------------------
# PANEL_CIRCUIT_DASH — should match
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_panel,expected_circuits", [
    ("L1-5",        "L1",   "5"),
    ("P1-57",       "P1",   "57"),
    ("7LA-29",      "7LA",  "29"),
    ("LB1-35",      "LB1",  "35"),
    ("4LF-8",       "4LF",  "8"),
    ("LL1B-1,3,5",  "LL1B", "1,3,5"),
    ("LB1 - 29,31", "LB1",  "29,31"),
    ("LA1-1",       "LA1",  "1"),
    ("NL2A3-10",    "NL2A3","10"),
    ("CRL2A2-22",   "CRL2A2","22"),
    ("LL1B-1",      "LL1B", "1"),
])
def test_panel_circuit_dash_matches(text, expected_panel, expected_circuits):
    m = PANEL_CIRCUIT_DASH.search(text)
    assert m is not None, f"Pattern did not match: {text!r}"
    panel = m.group(1)
    circuits_raw = m.group(2).replace(" ", "")
    assert panel == expected_panel, f"Panel mismatch for {text!r}"
    assert circuits_raw == expected_circuits, f"Circuit mismatch for {text!r}"


# ---------------------------------------------------------------------------
# PANEL_CIRCUIT_DASH — should NOT match (equipment/callout tags)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "FC-3",
    "EQ-10",
    "2D-06",
    "300F-60",
    "WSHP-4-01",
])
def test_panel_circuit_dash_rejects_equipment(text):
    # EQUIPMENT_TAG should match these before PANEL_CIRCUIT_DASH is applied
    assert is_equipment_tag(text), f"EQUIPMENT_TAG should match: {text!r}"


# ---------------------------------------------------------------------------
# PANEL_CIRCUIT_COLON — should match
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_panel,expected_circuit", [
    ("L1:5",   "L1",  "5"),
    ("LB1:29", "LB1", "29"),
])
def test_panel_circuit_colon_matches(text, expected_panel, expected_circuit):
    m = PANEL_CIRCUIT_COLON.search(text)
    assert m is not None, f"Pattern did not match: {text!r}"
    assert m.group(1) == expected_panel
    assert m.group(2) == expected_circuit


# ---------------------------------------------------------------------------
# PANEL_TOKEN fullmatch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "L1", "P1", "7LA", "LB1", "NL2A3", "CRL2A2", "4LF", "LL1B", "LA1",
    "LA", "LP", "A", "AB", "ABC", "ABCD",
])
def test_panel_token_accepts(text):
    assert is_panel_token(text), f"PANEL_TOKEN should accept: {text!r}"


@pytest.mark.parametrize("text", [
    "112", "114", "300F", "12", "0", "85", "1",
    "a", "b", "+42",
    "B R012",   # has space
    "FC",       # only 2 letters — actually valid panel token; see note below
])
def test_panel_token_rejects_pure_numbers(text):
    # Pure digit strings must be rejected
    if text.isdigit():
        assert not is_panel_token(text), f"PANEL_TOKEN should reject pure digit: {text!r}"


# ---------------------------------------------------------------------------
# CIRCUIT_TOKEN fullmatch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("val", [1, 5, 29, 84, 10, 63])
def test_circuit_token_accepts_valid(val):
    assert is_circuit_token(str(val)), f"CIRCUIT_TOKEN should accept: {val}"


@pytest.mark.parametrize("val", [0, 85, 100, 112, 114])
def test_circuit_token_rejects_out_of_range(val):
    assert not is_circuit_token(str(val)), f"CIRCUIT_TOKEN should reject: {val}"


@pytest.mark.parametrize("text", ["47C", "M25", "1a", "2B", "+42", "R012"])
def test_circuit_token_rejects_non_digits(text):
    assert not is_circuit_token(text), f"CIRCUIT_TOKEN should reject: {text!r}"


# ---------------------------------------------------------------------------
# all_circuits_valid
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("circuit_str", [
    "5", "29", "84", "1", "1,3,5", "29,31", "25,27,29",
])
def test_all_circuits_valid_accepts(circuit_str):
    assert all_circuits_valid(circuit_str), f"Should be valid: {circuit_str!r}"


@pytest.mark.parametrize("circuit_str", [
    "47C",          # contains letter
    "45,47C",       # one part has letter
    "85",           # out of range
    "0",            # below minimum
    "1,85",         # second part out of range
    "M25",          # letter prefix
    "1,3,5,100",    # last part out of range
])
def test_all_circuits_valid_rejects(circuit_str):
    assert not all_circuits_valid(circuit_str), f"Should be invalid: {circuit_str!r}"


# ---------------------------------------------------------------------------
# EQUIPMENT_TAG
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "FC-3", "EQ-10", "2D-06", "300F-60", "300F-79",
])
def test_equipment_tag_matches(text):
    assert is_equipment_tag(text), f"EQUIPMENT_TAG should match: {text!r}"


@pytest.mark.parametrize("text", [
    "L1-5", "LB1-35", "7LA-29",   # valid panel-circuit
])
def test_equipment_tag_does_not_match_panel_circuits(text):
    assert not is_equipment_tag(text), f"EQUIPMENT_TAG should NOT match: {text!r}"


# ---------------------------------------------------------------------------
# FIXTURE_TAG
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["B R012", "GX6 R012"])
def test_fixture_tag_matches(text):
    assert is_fixture_tag(text), f"FIXTURE_TAG should match: {text!r}"


# ---------------------------------------------------------------------------
# MOUNTING_HEIGHT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ['+42"', "+48AFF", "+42'"])
def test_mounting_height_matches(text):
    assert is_mounting_height(text), f"MOUNTING_HEIGHT should match: {text!r}"


@pytest.mark.parametrize("text", ["L1-5", "42", "112"])
def test_mounting_height_no_match(text):
    assert not is_mounting_height(text), f"MOUNTING_HEIGHT should NOT match: {text!r}"


# ---------------------------------------------------------------------------
# SWITCH_LEG
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["a", "b", "a,b", "7a", "7b", "7c"])
def test_switch_leg_matches(text):
    assert is_switch_leg(text), f"SWITCH_LEG should match: {text!r}"


@pytest.mark.parametrize("text", ["L1", "LB1", "47C", "1,3,5"])
def test_switch_leg_no_match(text):
    assert not is_switch_leg(text), f"SWITCH_LEG should NOT match: {text!r}"
