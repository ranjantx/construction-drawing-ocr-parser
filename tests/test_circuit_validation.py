"""Unit tests for circuit number validation rules."""

import pytest
from pipeline.regex_patterns import all_circuits_valid, is_circuit_token


class TestCircuitRange:
    """Boundary tests for valid circuit range 1-84."""

    def test_minimum_valid(self):
        assert is_circuit_token("1")

    def test_maximum_valid(self):
        assert is_circuit_token("84")

    def test_below_minimum(self):
        assert not is_circuit_token("0")

    def test_above_maximum(self):
        assert not is_circuit_token("85")

    def test_typical_values(self):
        for v in [5, 10, 29, 31, 42, 63, 79]:
            assert is_circuit_token(str(v)), f"Should accept {v}"

    def test_room_numbers_rejected(self):
        for v in [100, 112, 114, 200, 300]:
            assert not is_circuit_token(str(v)), f"Should reject room number {v}"


class TestCircuitWithLetters:
    """Letters in circuit numbers must always be rejected."""

    @pytest.mark.parametrize("text", [
        "47C", "M25", "1a", "2B", "R012", "3X", "10A",
    ])
    def test_rejects_letters(self, text):
        assert not is_circuit_token(text), f"Should reject: {text!r}"

    @pytest.mark.parametrize("circuit_str", [
        "45,47C", "1,3,5A", "M25,30",
    ])
    def test_rejects_partial_letter_list(self, circuit_str):
        assert not all_circuits_valid(circuit_str)


class TestCommaCircuits:
    """Comma-separated circuit lists."""

    @pytest.mark.parametrize("circuit_str,expected", [
        ("1,3,5",       True),
        ("29,31",       True),
        ("25,27,29",    True),
        ("1,84",        True),
        ("45,47C",      False),
        ("1,85",        False),
        ("0,2",         False),
        ("1,3,5,100",   False),
    ])
    def test_comma_lists(self, circuit_str, expected):
        result = all_circuits_valid(circuit_str)
        assert result == expected, f"Unexpected result for {circuit_str!r}: got {result}"


class TestMountingHeightNotCircuit:
    """+42" style strings must not pass circuit validation."""

    @pytest.mark.parametrize("text", ['+42"', "+48AFF", "+36'"])
    def test_mounting_height_is_not_circuit(self, text):
        assert not is_circuit_token(text)
        assert not all_circuits_valid(text)


class TestRoomNumbers:
    """3–4 digit integers above 84 must be rejected as circuits."""

    @pytest.mark.parametrize("text", ["112", "114", "200", "801", "1000"])
    def test_room_numbers_not_circuits(self, text):
        assert not is_circuit_token(text)
