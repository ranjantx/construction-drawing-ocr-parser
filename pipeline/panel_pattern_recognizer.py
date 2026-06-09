"""
Panel Label Pattern Recognizer.

Purpose
-------
A single electrical drawing uses one consistent panel naming convention.
This module discovers that convention automatically from the first pass
of extracted candidate labels, then uses it to:

  1. Accept labels that fit the dominant pattern.
  2. Flag / downgrade outliers that don't match.
  3. Provide a drawing-specific "panel whitelist" to boost confidence.

Algorithm
---------
1. Hard pre-filter: reject labels with spaces, length > 8, lowercase words,
   pure digits, or common English words (OWN, PANEL, SERVICE, etc.)
2. Generalise each surviving label into a TEMPLATE by collapsing letter runs
   to 'L' and digit runs to 'N':
       EL1     -> L-N
       UL1     -> L-N
       L8N3B2  -> L-N-L-N-L-N
       E       -> L
3. Count template frequencies and select the dominant template (≥ THRESHOLD).
4. Score each candidate label against the dominant template.

Typical results on the Power & Signal drawing
    L-N  (EL1, EL2, EL3, UL1, UL2, E, U)  78 % of candidates → dominant
    Rejects: "E201B" (L-N-L template, 1%), "PANEL" (word), "OWN" (word)
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

# ── Tunable constants ──────────────────────────────────────────────────────
# Fraction of labels that must share a template for it to be "dominant"
DOMINANT_THRESHOLD: float = 0.55

# Maximum label length to consider (after pre-filter)
MAX_LABEL_LEN: int = 8

# Common English words / drawing annotation words that are NOT panel labels.
# These pass the regex but are semantically invalid as panel identifiers.
_WORD_BLACKLIST: frozenset[str] = frozenset({
    # Generic words
    "PANEL", "SERVICE", "CEILING", "OWN", "DOWN", "OPEN", "EXIT",
    "MECH", "ELEC", "AREA", "ROOM", "ZONE", "UNIT", "TYPE",
    "LOAD", "FEED", "MAIN", "SUB", "NEW", "OLD",
    # Drawing metadata
    "DATE", "SCALE", "DRAWN", "SHEET", "REV", "REVD",
    # Drawing annotations
    "POWER", "LIGHT", "DATA", "SIGNAL", "NOTES", "NOTE",
    "SPEC", "GENERAL", "LEGEND", "SYMBOL", "MARK",
    # Reference / cross-reference tags (NOT panels)
    "REFEL", "REFER",
})
# ──────────────────────────────────────────────────────────────────────────


def _to_template(label: str) -> str:
    """
    Collapse consecutive letters into 'L' and consecutive digits into 'N'.
    Returns the structural template string.

    CRITICAL: Use a protected marker (lowercase) for digits so they don't get re-matched by [A-Z]+.

    Examples:
        EL1     -> "LN"
        UL1     -> "LN"
        L8N3B2  -> "LNLNLN"
        E       -> "L"
        P1      -> "LN"
        E201B   -> "LNL"
    """
    # Step 1: Replace digit runs with lowercase 'd' (protected marker, won't match [A-Z]+)
    protected = re.sub(r"\d+", "d", label)
    # Step 2: Replace uppercase letter runs with 'L' (won't match lowercase 'd')
    collapsed = re.sub(r"[A-Z]+", "L", protected)
    # Step 3: Replace marker 'd' with 'N'
    template = collapsed.replace("d", "N")
    return template


def _hard_prefilter(label: str) -> bool:
    """
    Return True if the label passes all hard rejection rules and is a valid
    panel label candidate; False if it should be immediately discarded.
    """
    # No spaces — "CEILING SERVICE PANEL-1" → reject
    if " " in label:
        return False

    # Length check
    if len(label) > MAX_LABEL_LEN:
        return False

    # Must contain at least one letter
    if not any(c.isalpha() for c in label):
        return False

    # Pure letter strings > 4 chars that are dictionary words → reject
    letters_only = re.sub(r"[^A-Z]", "", label.upper())
    if letters_only in _WORD_BLACKLIST:
        return False
    if len(letters_only) > 4 and letters_only in _WORD_BLACKLIST:
        return False

    # Reject strings with too many consecutive letters that form words
    # e.g. "OWN", "DOWN", "SERV" — check every 3+ letter run
    for match in re.finditer(r"[A-Z]{3,}", label.upper()):
        word = match.group()
        if word in _WORD_BLACKLIST:
            return False

    return True


class PanelPatternRecognizer:
    """
    Discovers and enforces the dominant panel label pattern in a drawing.
    """

    def __init__(self, threshold: float = DOMINANT_THRESHOLD):
        self.threshold   = threshold
        self.dominant_template: Optional[str] = None
        self.template_counts: Counter         = Counter()
        self.total_candidates: int            = 0
        self.discovered_panels: set[str]      = set()

    # ── Phase 1: learn from extracted candidates ──────────────────────────

    def fit(self, panel_labels: list[str]) -> "PanelPatternRecognizer":
        """
        Analyse a list of extracted panel label strings and identify the
        dominant structural template.  Call once after first-pass extraction.
        """
        candidates = [lbl for lbl in panel_labels if _hard_prefilter(lbl)]
        self.total_candidates = len(candidates)

        if not candidates:
            logger.warning("PanelPatternRecognizer.fit: no valid candidates found")
            return self

        self.template_counts = Counter(_to_template(lbl) for lbl in candidates)
        total = len(candidates)

        # Find dominant template (≥ threshold)
        for tmpl, count in self.template_counts.most_common():
            coverage = count / total
            if coverage >= self.threshold:
                self.dominant_template = tmpl
                dominant_count = count
                logger.info(
                    "Dominant panel template: %r  coverage=%.0f%%  (%d/%d labels)  "
                    "examples: %s",
                    tmpl, coverage * 100, dominant_count, total,
                    [lbl for lbl in candidates if _to_template(lbl) == tmpl][:8],
                )
                break

        if self.dominant_template is None:
            # No single template dominates; log top templates for debugging
            top = self.template_counts.most_common(3)
            logger.info(
                "No dominant panel template found (threshold %.0f%%). "
                "Top templates: %s",
                self.threshold * 100, top,
            )

        # Record all labels that match the dominant template
        if self.dominant_template:
            self.discovered_panels = {
                lbl for lbl in candidates
                if _to_template(lbl) == self.dominant_template
            }

        return self

    # ── Phase 2: score individual labels ─────────────────────────────────

    def score_label(self, label: str) -> float:
        """
        Return a quality score in [0.0, 1.0] for a single panel label.

          1.0  label passed hard-filter AND matches dominant template exactly
          0.85 label passed hard-filter AND is single-letter subset of dominant
          0.8  label passed hard-filter AND template is prefix/suffix of dominant
          0.5  label passed hard-filter but template doesn't match dominant (outlier)
          0.0  label failed hard-filter (spaces, word, too long, or invalid)

        Examples:
          EL1 (LN) in LN-dominant drawing    → 1.0 ✓
          E (L) in LN-dominant drawing       → 0.85 ✓
          E201B (LNLN) in LN-dominant        → 0.5 (doesn't match, outlier)
          REFEL2 (LLL) in LN-dominant        → 0.5 (doesn't match, outlier)
        """
        if not _hard_prefilter(label):
            return 0.0

        if self.dominant_template is None:
            # No pattern discovered → conservative accept
            return 0.6

        tmpl = _to_template(label)

        if tmpl == self.dominant_template:
            return 1.0

        # Partial match: dominant is "LN", label is "L" (single-letter panel like E, U)
        # Accept single-letter panels only if dominant starts with "L"
        if tmpl == "L" and self.dominant_template.startswith("L"):
            return 0.85

        # Partial match: label template starts with dominant (extended version, rare)
        # Example: dominant "LN", label "LNL" (extra suffix)
        # BUT: only allow if dominant template is at least 2 chars (don't accept "LNL" for dominant "L")
        if tmpl.startswith(self.dominant_template) and len(self.dominant_template) >= 2:
            return 0.80

        # No match: outlier template (possible OCR error or invalid panel)
        # Examples: E201B (LNL) when dominant is L; REFEL2 (LLL) when dominant is LN
        # LNL.startswith('L') is True but we now require dominant_template to be 2+ chars
        # Score 0.5 allows joiner to attempt (all_circuits_valid check catches truly invalid)
        return 0.5

    def is_valid_panel(self, label: str, min_score: float = 0.5) -> bool:
        """Quick boolean check."""
        return self.score_label(label) >= min_score

    def get_dominant_pattern_regex(self) -> Optional[str]:
        """
        Return a regex pattern corresponding to the dominant template.
        Useful for logging / debugging.
        """
        if not self.dominant_template:
            return None
        # Convert "LN" → "[A-Z]{1,4}\\d{1,2}" etc.
        mapping = {"L": "[A-Z]{1,4}", "N": "\\d{1,3}"}
        return "".join(mapping.get(c, re.escape(c)) for c in self.dominant_template)

    def summary(self) -> str:
        tmpl   = self.dominant_template or "(none)"
        regex  = self.get_dominant_pattern_regex() or "N/A"
        top3   = self.template_counts.most_common(3)
        panels = sorted(self.discovered_panels)[:10]
        return (
            f"PanelPatternRecognizer summary\n"
            f"  Candidates analysed : {self.total_candidates}\n"
            f"  Dominant template   : {tmpl!r}  (regex approx: {regex})\n"
            f"  Top-3 templates     : {top3}\n"
            f"  Sample valid panels : {panels}\n"
        )
