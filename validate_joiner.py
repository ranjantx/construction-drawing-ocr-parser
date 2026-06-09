"""
Validate join_circuit_continuations against all known good/bad cases.
"""
import sys; sys.path.insert(0, ".")
from models.data_models import BBox, OCRToken, PanelCircuitCandidate
from pipeline.classifier import classify_all
from pipeline.text_merger import join_circuit_continuations

def tok(text, x1, x2, y1=50, y2=70, conf=0.95):
    return OCRToken(raw_text=text, normalized_text=text.upper(), ocr_confidence=conf,
                    bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2), page=0)

# Average char width for "UL1-4,8,10,12" (14 chars, width ~160px) = ~11.4px
# TIGHT_GAP_CHARS=1.5 → threshold ≈ 17px

cases = [
    # ── SHOULD JOIN ──────────────────────────────────────────────────────────
    # The exact problem: "UL1-4,8,10,12" split from "14,16,18" by PaddleOCR
    ("SHOULD JOIN  UL1 split",
     [tok("UL1-4,8,10,12", x1=100, x2=260), tok("14,16,18", x1=265, x2=340)],
     "UL1", "4,8,10,12,14,16,18"),

    # EL2 long list split
    ("SHOULD JOIN  EL2 split",
     [tok("EL2-2,4,6,8,10,12,14", x1=100, x2=340), tok("20,27,29", x1=345, x2=420)],
     "EL2", "2,4,6,8,10,12,14,20,27,29"),

    # ── MUST NOT JOIN ────────────────────────────────────────────────────────
    # Separate annotations same line but large gap (>1.5× char width)
    ("MUST NOT JOIN separate annotations",
     [tok("EL2-13,15,22,24,33,35", x1=100, x2=400), tok("2,24", x1=460, x2=510)],
     "EL2", "13,15,22,24,33,35"),  # "2,24" is 60px away, too far

    # Right fragment is a standalone number (no comma) → must not join
    ("MUST NOT JOIN standalone number 14",
     [tok("UL1-4,8,10,12", x1=100, x2=260), tok("14", x1=263, x2=285)],
     "UL1", "4,8,10,12"),  # "14" alone has no comma, rejected

    # Right fragment starts with letters (separate panel annotation)
    ("MUST NOT JOIN new panel label",
     [tok("E-29", x1=100, x2=200), tok("UL1-5", x1=205, x2=330)],
     "E", "29"),  # UL1-5 starts with letters, ignored by joiner

    # "3,6" adjacent to panel-circuit: SHOULD join — conduit specs always have
    # non-digit chars (', ", 2R, _DAT). Pure digit+comma = circuit continuation.
    ("SHOULD JOIN  3,6 adjacent (circuit continuation)",
     [tok("L8N3B2-29", x1=100, x2=220), tok("3,6", x1=223, x2=260)],
     "L8N3B2", "29,3,6"),
]

for label, tokens, expected_panel, expected_circuit in cases:
    candidates = classify_all(tokens)
    joined = join_circuit_continuations(candidates)
    pc = [c for c in joined if c.classification == "panel_circuit"]
    if pc:
        result_panel   = pc[0].panel
        result_circuit = pc[0].circuit
        ok_panel   = result_panel   == expected_panel
        ok_circuit = result_circuit == expected_circuit
        status = "OK  " if (ok_panel and ok_circuit) else "FAIL"
        print(f"[{status}] {label}")
        if not ok_panel or not ok_circuit:
            print(f"       expected panel={expected_panel!r}  circuit={expected_circuit!r}")
            print(f"       got     panel={result_panel!r}  circuit={result_circuit!r}")
    else:
        print(f"[FAIL] {label} — no panel_circuit found at all")

# Extra: verify "3,6" doesn't cause a false join for conduit spec
print("\n--- Extra: 3,6 false join check ---")
tokens = [tok("L8N3B2-29", x1=100, x2=220), tok("3,6", x1=224, x2=260)]
candidates = classify_all(tokens)
joined = join_circuit_continuations(candidates)
pc = [c for c in joined if c.classification == "panel_circuit"]
if pc:
    print(f"  circuit={pc[0].circuit!r}  (ideally 29 only, but 29,3,6 is possible false join)")
    if pc[0].circuit == "29":
        print("  OK: conduit fragment not joined (gap too large OR failed valid check)")
    else:
        print("  NOTE: 3,6 was joined. Verify this is acceptable on real drawings.")
