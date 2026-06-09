"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from models.data_models import BBox, OCRToken

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PDF = FIXTURES_DIR / "sample_panel_labels.pdf"
GROUND_TRUTH = FIXTURES_DIR / "ground_truth.json"

# Session-scoped shared output dir — pipeline runs ONCE for all integration tests
_session_output: Path | None = None


@pytest.fixture(scope="session")
def pipeline_output_dir():
    """
    Runs extract_circuits pipeline once per test session and returns the output dir.
    Shared by all integration/accuracy tests to avoid re-running OCR 6 times.
    """
    global _session_output
    if not SAMPLE_PDF.exists():
        pytest.skip(f"Fixture PDF not found: {SAMPLE_PDF}")

    tmpdir = Path(tempfile.mkdtemp(prefix="parser_test_"))
    from extract_circuits import run_pipeline
    # Explicitly use easyocr so tests are deterministic regardless of PaddleOCR
    # runtime compatibility on the current platform (PaddleOCR 3.x has oneDNN
    # issues on Windows/Python 3.13 that make it silently return empty results).
    run_pipeline(str(SAMPLE_PDF), str(tmpdir), dpi=300, ocr_backend="easyocr")
    _session_output = tmpdir
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


def _token(text: str, x1=10.0, y1=10.0, x2=100.0, y2=30.0, page=0, conf=0.95) -> OCRToken:
    return OCRToken(
        raw_text=text,
        normalized_text=text,
        ocr_confidence=conf,
        bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2),
        page=page,
    )


@pytest.fixture
def make_token():
    return _token


@pytest.fixture
def sample_tokens():
    """Representative set of OCR tokens covering multiple classification categories."""
    return [
        _token("L1-5",       x1=100, y1=200, x2=150, y2=220),
        _token("LB1-29,31",  x1=200, y1=200, x2=270, y2=220),
        _token("+42\"",      x1=300, y1=200, x2=340, y2=220),
        _token("112",        x1=400, y1=200, x2=430, y2=220),
        _token("FC-3",       x1=500, y1=200, x2=540, y2=220),
        _token("B R012",     x1=600, y1=200, x2=650, y2=220),
        _token("7a",         x1=700, y1=200, x2=720, y2=220),
        _token("LA1",        x1=100, y1=300, x2=140, y2=320),
        _token("1",          x1=112, y1=325, x2=126, y2=340),  # below LA1
    ]
