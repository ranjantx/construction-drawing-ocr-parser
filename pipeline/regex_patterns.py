"""
All compiled regex patterns for electrical panel/circuit extraction.
All patterns are module-level constants — compiled once at import.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Panel-circuit compound patterns
# ---------------------------------------------------------------------------

# Handles: L1-5, 7LA-29, LB1 - 29,31, LL1B-1,3,5
# Accepts digit-letter prefix (e.g. 7LA) and letter-led (e.g. LB1)
# Dash variants: hyphen, en-dash, em-dash
PANEL_CIRCUIT_DASH = re.compile(
    r"\b([A-Z][A-Z0-9]{0,7}|[0-9][A-Z]{2,}[A-Z0-9]{0,4})"
    r"\s*[-–—]\s*"
    r"(\d{1,2}(?:\s*,\s*\d{1,2})*)\b"
)

# Handles: LB1:29
PANEL_CIRCUIT_COLON = re.compile(
    r"\b([A-Z][A-Z0-9]{0,7}|[0-9][A-Z]{2,}[A-Z0-9]{0,4})"
    r"\s*:\s*"
    r"(\d{1,2})\b"
)

# Handles: LB1 35 (space-separated on same OCR token, less common)
PANEL_CIRCUIT_SPACE = re.compile(
    r"\b([A-Z][A-Z0-9]{0,7}|[0-9][A-Z]{2,}[A-Z0-9]{0,4})"
    r"\s{1,3}"
    r"(\d{1,2}(?:\s*,\s*\d{1,2})*)\b"
)

# ---------------------------------------------------------------------------
# Standalone token patterns (fullmatch only)
# ---------------------------------------------------------------------------

# Standalone panel token:
#   letter-led:       L1, LB1, NL2A3, CRL2A2, LL1B, LA1, E, U, EL1, EL2
#   digit-letter-led: 7LA, 4LF  (single digit + 2+ uppercase letters required)
#
# Digit-prefix rule tightened (Change 4):
#   OLD: [0-9][A-Z][A-Z0-9]{0,5}  — matched "1L1" (digit+1letter+digit = OCR artifact of "EL1")
#   NEW: [0-9][A-Z]{2,}[A-Z0-9]{0,4} — single digit MUST be followed by 2+ letters
#   This keeps 7LA, 4LF, 7LA2 but rejects 1L1, 1E, 1L (OCR misreads of EL1, E, L)
PANEL_TOKEN = re.compile(
    r"^([A-Z]{1,4}[A-Z0-9]{0,5}|[0-9][A-Z]{2,}[A-Z0-9]{0,4})$"
)

# Standalone circuit token: integers 1-84 only
CIRCUIT_TOKEN = re.compile(
    r"^([1-9]|[1-7][0-9]|8[0-4])$"
)

# Multi-circuit standalone list: 1,3,5 or 25,27,29 (all parts validated separately)
MULTI_CIRCUIT = re.compile(
    r"^(\d{1,2})(?:,(\d{1,2}))+$"
)

# ---------------------------------------------------------------------------
# Rejection patterns (checked BEFORE panel-circuit patterns)
# ---------------------------------------------------------------------------

# Equipment / detail / callout tag: FC-3, EQ-10, 2D-06, 300F-60, WSHP-4-01
# Three sub-patterns (applied in order, all full-match):
#   1. 2–4 pure letters + dash + 1–3 digits + optional letter : FC-3, EQ-10
#   2. 1–3 digits + EXACTLY 1 letter + dash + 1–3 digits     : 2D-06, 300F-60
#      (uses [A-Z]{1} to ensure only ONE letter — blocks 7LA / 4LF which have 2 letters)
#   3. 2–6 pure letters + dash + 1–2 digits + dash + 2–4 digits : WSHP-4-01, AHU-1-01
EQUIPMENT_TAG = re.compile(
    r"^(?:"
    r"[A-Z]{2,4}-\d{1,3}[A-Z]?"
    r"|[0-9]{1,3}[A-Z]{1}-\d{1,3}[A-Z]?"
    r"|[A-Z]{2,6}-\d{1,2}-\d{2,4}"
    r")$"
)

# Fixture / device tag: B R012, GX6 R012
FIXTURE_TAG = re.compile(
    r"^[A-Z0-9]{1,4}\s+R\d{3,}$"
)

# Mounting height: +42", +48AFF, +42'
MOUNTING_HEIGHT = re.compile(
    r'^\+\d+["“”\'A-Z]*$'
)

# Switch leg / control label: a, b, a,b, 7a, 7b, 7c
SWITCH_LEG = re.compile(
    r"^[0-9]{0,2}[a-d](?:,[0-9]{0,2}[a-d])*$"
)

# Room number pattern: 3-4 digit pure integer
ROOM_NUMBER_PURE = re.compile(
    r"^\d{3,4}$"
)

# Alphanumeric room codes: BH0G.024, 8.024
ROOM_CODE = re.compile(
    r"^[A-Z0-9]{2,4}\.[0-9]{3}$"
)

# Conduit / cable specification tag.
# Examples from electrical drawings:
#   "3' 6\"-2R_DAT-2"  "1' 6\"-2R-3"  "3'6\"-2R-1"  "?-?-1' 6\"-Quad-5"
#   "8UL-23-36-2R-4"   "48UL-25-36-2R-5"
# Detected by presence of: foot ('), inch ("), wire-type keywords, or ?-? prefix.
CONDUIT_SPEC = re.compile(
    r"(?:"
    r"\d+'\s*\d*\"?"         # foot marker:  3' or 3'6"
    r"|[\"]\d"               # inch marker:  "2
    r"|\d+\s*\"-"            # inches-dash:  6"-
    r"|[-–]\d+R\b"           # wire count:   -2R -3R
    r"|[?][^a-zA-Z0-9]"      # OCR unknown:  ?-?
    r"|QUAD|TWIST|_DAT|_2R"  # cable type keywords
    r")"
)

# Dash normalizer — replaces en/em/various dashes with ASCII hyphen
DASH_NORMALIZER = re.compile(
    r"[–—−﹘﹣－]"
)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def all_circuits_valid(circuit_str: str) -> bool:
    """
    Returns True only if every comma-separated part is a pure integer in [1, 84].
    Rejects: '45,47C' (47C not digit), '1,85' (85 out of range), '0,2' (0 invalid).
    """
    for part in circuit_str.split(","):
        part = part.strip()
        if not part.isdigit():
            return False
        val = int(part)
        if val < 1 or val > 84:
            return False
    return True


def looks_like_panel_label(text: str, known_panels: set[str] | None = None) -> bool:
    """
    Quality gate beyond PANEL_TOKEN regex — rejects OCR noise and dictionary
    words that are clearly not electrical panel labels.

    Rules (applied in order):
    1. If text is in known_panels → always accept.
    2. Text must NOT start with punctuation (,;.?!' etc.) — OCR artifact.
    3. Text must contain at least one digit. Pure-letter tokens like CORRIDOR,
       ROOM, BIOLOGY are room labels / notes (exception: single-letter panels
       like E, U are common — they are accepted only via the dash pattern;
       the space/geometry path requires a digit).
    4. Digit-prefix tokens (e.g. "7LA") must have ≥2 letters after the digit.
       "1L1" has only 1 letter between two digits → OCR misread of "EL1".
    5. Length must be ≤ 7 characters.

    Returns True only when the text passes all active rules.
    """
    if known_panels and text.upper() in known_panels:
        return True

    # Rule 2: no leading punctuation (OCR artifact ,1L1 etc.)
    if text and text[0] in ",;.?!'\"([{":
        return False

    # Rule 3: must contain at least one digit
    if not any(ch.isdigit() for ch in text):
        return False

    # Rule 4: digit-prefix tokens need ≥2 consecutive uppercase letters
    if text and text[0].isdigit():
        # Count leading letters after the opening digit
        letters_after = 0
        for ch in text[1:]:
            if ch.isalpha():
                letters_after += 1
            else:
                break
        if letters_after < 2:
            return False   # rejects "1L1", "1E", "1L", "8A"

    # Rule 5: reject unusually long tokens
    if len(text) >= 8:
        return False

    return True


def is_panel_token(text: str) -> bool:
    return bool(PANEL_TOKEN.fullmatch(text))


def is_circuit_token(text: str) -> bool:
    return bool(CIRCUIT_TOKEN.fullmatch(text))


def is_equipment_tag(text: str) -> bool:
    return bool(EQUIPMENT_TAG.fullmatch(text))


def is_fixture_tag(text: str) -> bool:
    return bool(FIXTURE_TAG.fullmatch(text))


def is_mounting_height(text: str) -> bool:
    return bool(MOUNTING_HEIGHT.fullmatch(text))


def is_switch_leg(text: str) -> bool:
    return bool(SWITCH_LEG.fullmatch(text))
