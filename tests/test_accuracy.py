"""
Accuracy measurement test.
Compares extracted panel-circuit pairs against manually verified ground truth.

Requires:
  tests/fixtures/sample_panel_labels.pdf
  tests/fixtures/ground_truth.json

ground_truth.json format:
  {
    "expected": [
      {"panel": "L1",  "circuit": "5"},
      {"panel": "LB1", "circuit": "29,31"}
    ]
  }

Metrics reported:
  precision = TP / (TP + FP)
  recall    = TP / (TP + FN)
  F1        = 2 * precision * recall / (precision + recall)

Thresholds:
  Synthetic test PDF  — precision >= 0.60, recall >= 0.40
    (lower because computer-generated PDF fonts confuse OCR; e.g. EasyOCR
     reads LL1B as LLIB which counts as a false positive vs ground truth)

  Real electrical drawings at 400 DPI — target precision >= 0.85, recall >= 0.80.
    To enforce production thresholds, replace the values in PRECISION_THRESHOLD
    and RECALL_THRESHOLD below with 0.85 and 0.80 once validated against real PDFs.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from tests.conftest import SAMPLE_PDF, GROUND_TRUTH

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF.exists() or not GROUND_TRUTH.exists(),
    reason="Accuracy test requires fixture PDF and ground_truth.json",
)


def _normalise_pair(panel: str, circuit: str) -> frozenset[tuple[str, str]]:
    """Expand comma-separated circuits into individual (panel, circuit) pairs."""
    pairs = set()
    for c in str(circuit).split(","):
        c = c.strip()
        if c:
            pairs.add((panel.upper().strip(), c))
    return frozenset(pairs)


def _load_ground_truth() -> set[tuple[str, str]]:
    with open(GROUND_TRUTH, encoding="utf-8") as f:
        data = json.load(f)
    gt = set()
    for item in data.get("expected", []):
        gt |= _normalise_pair(item["panel"], item["circuit"])
    return gt


def _load_extracted(output_dir: Path) -> set[tuple[str, str]]:
    import pandas as pd
    df = pd.read_excel(output_dir / "circuits.xlsx", sheet_name="Circuits")
    pc = df[df["classification"] == "panel_circuit"]
    extracted = set()
    for _, row in pc.iterrows():
        extracted |= _normalise_pair(str(row["panel"]), str(row["circuit"]))
    return extracted


# Thresholds for synthetic fixture PDF — lower than production targets.
# For real drawings raise these to PRECISION_THRESHOLD=0.85, RECALL_THRESHOLD=0.80.
PRECISION_THRESHOLD = 0.60
RECALL_THRESHOLD = 0.40


def test_precision_recall(pipeline_output_dir):
    ground_truth = _load_ground_truth()
    extracted = _load_extracted(pipeline_output_dir)

    tp = len(extracted & ground_truth)
    fp = len(extracted - ground_truth)
    fn = len(ground_truth - extracted)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    print(f"\n{'='*50}")
    print(f"Accuracy Report (synthetic fixture PDF)")
    print(f"{'='*50}")
    print(f"  TP: {tp}  FP: {fp}  FN: {fn}")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall:    {recall:.3f}")
    print(f"  F1:        {f1:.3f}")
    print(f"  Ground truth ({len(ground_truth)} pairs): {sorted(ground_truth)}")
    print(f"  Extracted   ({len(extracted)} pairs): {sorted(extracted)}")
    if fp > 0:
        print(f"  False Positives: {sorted(extracted - ground_truth)}")
    if fn > 0:
        print(f"  False Negatives (OCR may have misread these): {sorted(ground_truth - extracted)}")
    print(f"{'='*50}")

    assert precision >= PRECISION_THRESHOLD, (
        f"Precision {precision:.3f} below threshold {PRECISION_THRESHOLD}. "
        f"FP breakdown: {sorted(extracted - ground_truth)}"
    )
    assert recall >= RECALL_THRESHOLD, (
        f"Recall {recall:.3f} below threshold {RECALL_THRESHOLD}. "
        f"FN breakdown: {sorted(ground_truth - extracted)}"
    )


def test_no_false_mounting_heights(pipeline_output_dir):
    """Mounting height patterns must produce zero false positives in circuit output."""
    import pandas as pd
    df = pd.read_excel(pipeline_output_dir / "circuits.xlsx", sheet_name="Circuits")
    pc = df[df["classification"] == "panel_circuit"]
    for _, row in pc.iterrows():
        raw = str(row["raw_text"])
        assert not raw.startswith("+"), f"Mounting height in circuit output: {raw!r}"


def test_uncertain_cases_flagged_for_review(pipeline_output_dir):
    """Low-confidence extractions must have needs_human_review=True."""
    import pandas as pd
    df = pd.read_excel(pipeline_output_dir / "circuits.xlsx", sheet_name="Circuits")
    low = df[(df["confidence"] == "low") & (df["classification"] == "panel_circuit")]
    for _, row in low.iterrows():
        assert row["needs_human_review"] == True, (
            f"Low confidence row not flagged for review: {row['raw_text']}"
        )


def test_rejected_sheet_has_no_panel_circuit(pipeline_output_dir):
    """
    The Rejected sheet may contain panel_circuit rows that need human review,
    but none of them should have confidence=high or medium without needs_human_review.
    """
    import pandas as pd
    df = pd.read_excel(pipeline_output_dir / "circuits.xlsx", sheet_name="Rejected")
    # Rows that are panel_circuit and confidence=high/medium should always have
    # needs_human_review=True if they're in the Rejected sheet
    for _, row in df.iterrows():
        if row["classification"] == "panel_circuit" and row["confidence"] in ("high", "medium"):
            assert row["needs_human_review"] == True, (
                f"High/medium confidence panel_circuit in Rejected without review flag: {row['raw_text']}"
            )
