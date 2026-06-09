"""
Generate a synthetic electrical-drawing PDF for integration testing.
Run once: python tests/create_test_pdf.py
Creates: tests/fixtures/sample_panel_labels.pdf
         tests/fixtures/ground_truth.json
"""

from __future__ import annotations

import json
from pathlib import Path

import fitz  # PyMuPDF

FIXTURES = Path(__file__).parent / "fixtures"
OUT_PDF = FIXTURES / "sample_panel_labels.pdf"
OUT_GT = FIXTURES / "ground_truth.json"

# (text, x, y, font_size)  — simulates what OCR would see on a lighting plan
ANNOTATIONS = [
    # clear panel-circuit compound tokens
    ("L1-5",       100, 150, 10),
    ("P1-57",      200, 150, 10),
    ("7LA-29",     300, 150, 10),
    ("LB1-35",     400, 150, 10),
    ("4LF-8",      500, 150, 10),
    ("LL1B-1,3,5", 100, 200, 10),
    ("LB1-29,31",  250, 200, 10),
    # two-token panel+circuit (geometry association needed)
    ("LA1",        100, 300, 10),
    ("1",          103, 315, 10),   # directly below LA1
    # noise — must be rejected
    ('+42"',       400, 300, 10),
    ("112",        500, 300, 10),
    ("FC-3",       100, 400, 10),
    ("EQ-10",      200, 400, 10),
    ("B R012",     300, 400, 10),
    ("7a",         400, 400, 10),
    ("300F-60",    500, 400, 10),
    # panel schedule header (triggers panel_validator)
    ("PANEL SCHEDULE", 100, 500, 14),
    ("L1",         130, 520, 10),
    ("P1",         180, 520, 10),
    ("7LA",        230, 520, 10),
    ("LB1",        280, 520, 10),
    ("4LF",        330, 520, 10),
    ("LL1B",       380, 520, 10),
    ("LA1",        440, 520, 10),
]

GROUND_TRUTH = {
    "expected": [
        {"panel": "L1",   "circuit": "5"},
        {"panel": "P1",   "circuit": "57"},
        {"panel": "7LA",  "circuit": "29"},
        {"panel": "LB1",  "circuit": "35"},
        {"panel": "4LF",  "circuit": "8"},
        {"panel": "LL1B", "circuit": "1,3,5"},
        {"panel": "LB1",  "circuit": "29,31"},
        {"panel": "LA1",  "circuit": "1"},
    ]
}


def create():
    FIXTURES.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # US letter

    for text, x, y, fs in ANNOTATIONS:
        page.insert_text((x, y), text, fontsize=fs, color=(0, 0, 0))

    doc.save(str(OUT_PDF))
    doc.close()
    print(f"PDF written: {OUT_PDF}")

    OUT_GT.write_text(json.dumps(GROUND_TRUTH, indent=2))
    print(f"Ground truth written: {OUT_GT}")


if __name__ == "__main__":
    create()
