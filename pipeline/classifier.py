"""
Token classification — 9-step decision tree.
ORDER IS CRITICAL: rejection patterns checked before panel-circuit patterns.

Classification labels:
  panel_circuit       — matched panel + valid circuit(s)
  multi_circuit       — comma-separated circuit list without a panel token
  mounting_height     — +42", +48AFF
  room_number         — pure integer > 84, or 3-4 digit code
  equipment_tag       — 300F-60, FC-3, EQ-10, 2D-06
  fixture_device_tag  — B R012, GX6 R012
  switch_leg          — a, b, 7a, a,b
  detail_callout      — hexagon numbers, sheet references
  unknown             — everything else (may be resolved by geometry pass)
"""

from __future__ import annotations

import re

from models.data_models import OCRToken, PanelCircuitCandidate
from pipeline.regex_patterns import (
    CIRCUIT_TOKEN,
    EQUIPMENT_TAG,
    FIXTURE_TAG,
    MOUNTING_HEIGHT,
    MULTI_CIRCUIT,
    PANEL_CIRCUIT_COLON,
    PANEL_CIRCUIT_DASH,
    PANEL_CIRCUIT_SPACE,
    PANEL_TOKEN,
    ROOM_NUMBER_PURE,
    SWITCH_LEG,
    all_circuits_valid,
    is_equipment_tag,
    is_panel_token,
    looks_like_panel_label,
)

# Known-panels cache — populated by the pipeline before classify_all() is called.
# Shared mutable set; set_known_panels() is called once per pipeline run.
_known_panels: set[str] = set()


def set_known_panels(panels: set[str]) -> None:
    """Inject the discovered panel list so the classifier can use looks_like_panel_label."""
    global _known_panels
    _known_panels = panels

# Detail/callout patterns: FC-3, EQ-10, 2D-06, and generic sheet-ref patterns
_DETAIL_CALLOUT = re.compile(
    r"^(?:[A-Z]{1,2}\d{1,2}|\d[A-Z]-\d{2,3}|[A-Z]{2,3}-\d{2,3})$"
)


def classify_token(token: OCRToken) -> PanelCircuitCandidate:
    """
    Classify a single OCRToken using the 9-step decision tree.
    Returns a PanelCircuitCandidate (classification may still be 'unknown'
    if geometry pass is needed).
    """
    text = token.normalized_text.strip()

    # Step 1 — Mounting height: +42", +48AFF
    if MOUNTING_HEIGHT.fullmatch(text):
        return PanelCircuitCandidate(
            token=token, classification="mounting_height",
            reason="Matches mounting height pattern (+digits[units])",
        )

    # Step 2 — Switch leg / control label: a, b, 7a, a,b
    if SWITCH_LEG.fullmatch(text):
        return PanelCircuitCandidate(
            token=token, classification="switch_leg",
            reason="Matches switch leg pattern (lowercase letter(s))",
        )

    # Step 3 — Fixture / device tag: B R012, GX6 R012
    if FIXTURE_TAG.fullmatch(text):
        return PanelCircuitCandidate(
            token=token, classification="fixture_device_tag",
            reason="Matches fixture/device tag pattern (alphanum + R-number)",
        )

    # Step 4 — Equipment / callout tag: FC-3, EQ-10, 2D-06, 300F-60
    # MUST come before PANEL_CIRCUIT_DASH to prevent false panel matches
    if EQUIPMENT_TAG.fullmatch(text):
        return PanelCircuitCandidate(
            token=token, classification="equipment_tag",
            reason="Matches equipment/callout tag pattern",
        )

    # Step 5 — Panel-circuit dash, colon, or space compound token
    for pattern, label, require_digit in [
        (PANEL_CIRCUIT_DASH,  "dash",  False),   # dash: strongest signal, no extra gate
        (PANEL_CIRCUIT_COLON, "colon", True),    # colon: also require digit (rejects DATE:28)
        (PANEL_CIRCUIT_SPACE, "space", True),    # space: weakest — require digit in panel
    ]:
        m = pattern.search(text)
        if m:
            panel_str = m.group(1)
            circuits_raw = m.group(2).replace(" ", "")

            panel_ok = is_panel_token(panel_str) and all_circuits_valid(circuits_raw)
            # Extra quality gate for space-separated matches:
            # reject pure-letter tokens like CORRIDOR, ROOM, BIOLOGY, E, R …
            if require_digit and panel_ok:
                panel_ok = looks_like_panel_label(panel_str, _known_panels)

            if panel_ok:
                return PanelCircuitCandidate(
                    token=token,
                    classification="panel_circuit",
                    panel=panel_str,
                    circuit=circuits_raw,
                    reason=f"Regex {label} match: panel={panel_str} circuits={circuits_raw}",
                )
            else:
                return PanelCircuitCandidate(
                    token=token, classification="unknown",
                    reason=f"Regex {label} match failed validation (panel_ok={is_panel_token(panel_str)}, "
                           f"circuits_ok={all_circuits_valid(circuits_raw)}, "
                           f"looks_like_panel={looks_like_panel_label(panel_str, _known_panels)})",
                )

    # Step 6 — Room number: pure integer > 84, or 3-4 digit code
    if ROOM_NUMBER_PURE.fullmatch(text):
        val = int(text)
        if val > 84:
            return PanelCircuitCandidate(
                token=token, classification="room_number",
                reason=f"Pure integer {val} > 84 — likely room number",
            )

    # Step 7 — Standalone valid circuit token (1-84): unknown until geometry confirms
    if CIRCUIT_TOKEN.fullmatch(text):
        return PanelCircuitCandidate(
            token=token, classification="unknown",
            reason="Standalone circuit token — awaiting geometry association",
        )

    # Step 8 — Standalone panel token: unknown until geometry confirms
    if PANEL_TOKEN.fullmatch(text):
        return PanelCircuitCandidate(
            token=token, classification="unknown",
            reason="Standalone panel token — awaiting geometry association",
        )

    # Step 9 — Multi-circuit list: 1,3,5 (validate all parts)
    if MULTI_CIRCUIT.search(text):
        if all_circuits_valid(text):
            return PanelCircuitCandidate(
                token=token, classification="multi_circuit",
                circuit=text,
                reason="Multi-circuit list without panel — needs geometry to associate",
            )

    # Default
    return PanelCircuitCandidate(
        token=token, classification="unknown",
        reason="No pattern matched",
    )


def classify_all(
    tokens: list[OCRToken],
    known_panels: set[str] | None = None,
) -> list[PanelCircuitCandidate]:
    """
    Classify a list of tokens. Geometry pass happens separately.
    Pass known_panels to enable the looks_like_panel_label quality gate.
    """
    if known_panels is not None:
        set_known_panels(known_panels)
    return [classify_token(t) for t in tokens]
