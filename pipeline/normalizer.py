"""
Text normalisation for OCR tokens.
- Normalise all dash variants to ASCII hyphen
- Lowercase l → uppercase L (OCR confusion for panel labels)
- O/0 disambiguation when known_panels context is available
- Preserve original raw_text separately (done by caller via OCRToken.raw_text)
"""

from __future__ import annotations

import re

from pipeline.regex_patterns import DASH_NORMALIZER

# Characters that look like lowercase L but should be uppercase L in panel context
_L_CONFUSION = re.compile(r"(?<=[A-Z0-9])l(?=[A-Z0-9])|^l(?=[A-Z0-9])|(?<=[A-Z0-9])l$")


def normalize_text(raw: str, known_panels: set[str] | None = None) -> str:
    """
    Return a normalised version of raw OCR text.
    Does NOT mutate raw — caller must store raw_text before calling.

    Steps:
    1. Strip surrounding whitespace
    2. Strip leading OCR-artifact punctuation (,;.?!' etc.) — panel labels
       never start with a comma, quote, or question mark.  These arise from
       drawing elements (lines, arrowheads) being misread by OCR.
    3. Collapse internal multi-spaces to single space
    4. Normalise all dash variants → ASCII hyphen
    5. Uppercase the whole string (panel labels are uppercase)
    6. O/0 disambiguation: if known_panels provided, try both forms
    """
    text = raw.strip()

    # Step 2 — strip leading OCR artifacts
    text = re.sub(r"^[,;.?!'\"()\[\]{}<>\\/*&#@~|]+", "", text).strip()

    text = re.sub(r"  +", " ", text)
    text = DASH_NORMALIZER.sub("-", text)
    text = text.upper()

    if known_panels:
        text = _disambiguate_o_zero(text, known_panels)

    return text


def _disambiguate_o_zero(text: str, known_panels: set[str]) -> str:
    """
    For each O in text, try replacing with 0 and vice versa.
    If exactly one variant matches a known panel, return that variant.
    Applies only to the panel-label portion (before any dash).
    """
    dash_idx = text.find("-")
    if dash_idx == -1:
        candidate = text
        suffix = ""
    else:
        candidate = text[:dash_idx]
        suffix = text[dash_idx:]

    variants = _generate_o_zero_variants(candidate)
    matches = [v for v in variants if v in known_panels]
    if len(matches) == 1:
        return matches[0] + suffix
    return text


def _generate_o_zero_variants(text: str) -> list[str]:
    """Generate all variants by substituting O↔0 at each position."""
    variants = set()
    for i, ch in enumerate(text):
        if ch == "O":
            variants.add(text[:i] + "0" + text[i+1:])
        elif ch == "0":
            variants.add(text[:i] + "O" + text[i+1:])
    variants.add(text)
    return list(variants)
