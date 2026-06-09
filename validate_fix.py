"""Validate all screenshot cases after the conservative merger fix."""
import sys; sys.path.insert(0, ".")
from models.data_models import BBox, OCRToken
from pipeline.text_merger import merge_text_lines
from pipeline.classifier import classify_all


def tok(text, x1, x2, y1=50, y2=65, page=0):
    return OCRToken(raw_text=text, normalized_text=text.upper(), ocr_confidence=0.9,
                    bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2), page=page)


tokens = [
    # SHOULD merge (split circuit list — the original problem)
    tok("UL1-4,8,10,12",          x1=100, x2=280, y1=50,  y2=65),
    tok("14,16,18",                x1=284, x2=380, y1=50,  y2=65),
    # MUST NOT merge (two separate annotations on same line)
    tok("EL2-19,21,23,25",         x1=400, x2=630, y1=50,  y2=65),
    tok("UL1-18,23,25,27,29",      x1=640, x2=870, y1=50,  y2=65),
    # MUST NOT merge (conduit spec follows panel-circuit on same line)
    tok("L8N3B2-29",               x1=100, x2=220, y1=120, y2=135),
    tok("3' 6\"-2R_DAT-2",         x1=225, x2=400, y1=120, y2=135),
    # MUST be conduit_spec (full merged conduit tag)
    tok("8UL-23-36-2R-4",          x1=100, x2=310, y1=180, y2=195),
    # MUST be conduit_spec (title block date)
    tok("?-?-1' 6\"-Quad-5",       x1=100, x2=280, y1=240, y2=255),
    tok("Date: 28 Apr 2026",        x1=100, x2=300, y1=300, y2=315),
    # Valid — long list, no split needed
    tok("UL2-1,3,5,7,9,11,13,15",  x1=10,  x2=300, y1=380, y2=395),
    # Valid — short
    tok("L2-10",                    x1=100, x2=160, y1=440, y2=455),
    tok("E-11",                     x1=200, x2=260, y1=440, y2=455),
    # Room number — must be filtered
    tok("156",                      x1=300, x2=340, y1=440, y2=455),
]

merged = merge_text_lines(tokens)
candidates = classify_all(merged)

LABEL = {
    "panel_circuit":  "CORRECT ",
    "conduit_spec":   "FILTERED",
    "room_number":    "FILTERED",
    "equipment_tag":  "FILTERED",
    "mounting_height":"FILTERED",
    "unknown":        "PENDING ",
}

print("\n=== Classification results ===")
all_ok = True
for c in candidates:
    m = LABEL.get(c.classification, "       ")
    print(f"  [{m}] {c.classification:<22}  {c.token.raw_text!r}")
    if c.classification == "panel_circuit":
        print(f"           -> panel={c.panel}  circuit={c.circuit}")

# Assertions
pc = [c for c in candidates if c.classification == "panel_circuit"]
panel_texts = [c.token.raw_text for c in pc]

assert "UL1-4,8,10,12,14,16,18" in panel_texts,  "FAIL: split list not merged"
assert "EL2-19,21,23,25" in panel_texts,           "FAIL: EL2 lost"
assert "UL1-18,23,25,27,29" in panel_texts,        "FAIL: UL1-18 lost"
assert "L8N3B2-29" in panel_texts,                 "FAIL: L8N3B2-29 lost"
assert "UL2-1,3,5,7,9,11,13,15" in panel_texts,   "FAIL: long UL2 list lost"
assert "L2-10" in panel_texts,                     "FAIL: L2-10 lost"
assert "E-11" in panel_texts,                      "FAIL: E-11 lost"

conduit = [c for c in candidates if c.classification == "conduit_spec"]
conduit_texts = [c.token.raw_text for c in conduit]
assert any("2R" in t or "Quad" in t for t in conduit_texts), "FAIL: conduit spec not filtered"

# L8N3B2-29 panel should have circuit=29 (conduit spec NOT merged in)
lb = next(c for c in pc if c.token.raw_text == "L8N3B2-29")
assert lb.circuit == "29",  f"FAIL: L8N3B2 circuit should be 29, got {lb.circuit}"
assert "2R" not in lb.circuit, "FAIL: conduit spec leaked into circuit"

# Date text must NOT be a panel_circuit
panel_names = [c.panel for c in pc if c.panel]
assert "DATE" not in panel_names, "FAIL: Date text classified as panel_circuit"

print("\nAll assertions passed.")
