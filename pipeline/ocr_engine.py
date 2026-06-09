"""
OCR engine — supports PaddleOCR (2.x / 3.x) and EasyOCR backends.

Supported backends
------------------
paddle   : PaddleOCR — higher accuracy, best for engineering drawings.
           v3.x tries PP-OCRv4 models first (avoids oneDNN/PIR bug on
           Windows/Python 3.13), then falls back to PP-OCRv5 default.
easyocr  : EasyOCR — reliable CPU fallback, pure-pip install, all platforms.
auto     : (default) tries PaddleOCR first; if smoke-test fails, uses EasyOCR.

CLI usage
---------
  --ocr-backend paddle
  --ocr-backend easyocr
  --ocr-backend auto        (default)

Environment flags set at module import (before PaddlePaddle C-extension loads)
-------------------------------------------------------------------------------
  FLAGS_use_mkldnn=0          disable MKL-DNN / oneDNN
  FLAGS_enable_pir_api=0      disable PIR (Program Internal Representation)
  FLAGS_new_executor_use_inplace=0
  CUDA_VISIBLE_DEVICES=""     force CPU
"""

from __future__ import annotations

import logging
import os

# ── These MUST be set before paddle's C-extension is loaded ──────────────────
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_new_executor_use_inplace", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
# ─────────────────────────────────────────────────────────────────────────────

import numpy as np

logger = logging.getLogger(__name__)

_backend: str | None = None   # "paddle" | "easyocr"
_paddle_engine = None         # (engine_object, version_int)
_easyocr_reader = None


# ---------------------------------------------------------------------------
# Public control API
# ---------------------------------------------------------------------------

def set_backend(name: str) -> None:
    """
    Force a specific backend before the first OCR call.
    name: "paddle" | "easyocr" | "auto"
    """
    global _backend
    assert name in ("paddle", "easyocr", "auto"), f"Unknown backend: {name!r}"
    _backend = None if name == "auto" else name
    logger.info("OCR backend set to: %s", name)


def get_active_backend() -> str:
    """Return the name of the backend that was actually initialised, or 'none'."""
    if _backend == "paddle" and _paddle_engine is not None:
        _, ver = _paddle_engine
        return f"paddle-v{ver}"
    if _backend == "easyocr" and _easyocr_reader is not None:
        return "easyocr"
    return "none (not yet initialised)"


def get_requested_backend() -> str:
    """
    Return the backend that was requested via set_backend() — useful for
    choosing the correct image preprocessing BEFORE the first OCR call.
    Returns 'auto' if no specific backend was forced.
    """
    return _backend if _backend is not None else "auto"


def get_engine():
    """
    Return the actual initialized OCR engine object.
    Initializes it if not already done.
    Returns either the PaddleOCR engine or EasyOCR reader.
    """
    _ensure_engine()
    if _backend == "paddle" and _paddle_engine is not None:
        return _paddle_engine[0]
    if _backend == "easyocr" and _easyocr_reader is not None:
        return _easyocr_reader
    return None


# ---------------------------------------------------------------------------
# PaddleOCR initialisation — tries multiple model variants
# ---------------------------------------------------------------------------

def _paddle_smoke_test(eng) -> bool:
    """
    Run OCR on a small image that contains real text.
    Blank images can skip inference and hide runtime errors.
    Returns True if the engine works end-to-end without exceptions.
    """
    import cv2
    dummy = np.ones((120, 400, 3), dtype=np.uint8) * 255
    cv2.putText(dummy, "L1-5 LB1-29", (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 0), 3)
    eng.ocr(dummy)   # raises on Windows PIR/oneDNN bug
    return True


def _try_init_paddle() -> tuple:
    """
    Try to initialise PaddleOCR.

    For PaddleOCR 3.x, attempts multiple model variants in priority order:
      1. PP-OCRv4  — avoids the PIR/oneDNN bug on Windows/Python 3.13
      2. PP-OCRv3  — older, more portable fallback
      3. default   — PP-OCRv5 (may fail on Windows with current PaddlePaddle)

    Returns (engine, version_int) on success, or (None, 0) on failure.
    """
    try:
        from paddleocr import PaddleOCR
        import paddleocr as _poc

        ver = int(getattr(_poc, "__version__", "2").split(".")[0])
        logger.info("PaddleOCR package version: %s", getattr(_poc, "__version__", "?"))

        if ver >= 3:
            # PaddleOCR 3.x — try model variants newest-to-oldest-compatible
            variants = [
                ("PP-OCRv4", {"ocr_version": "PP-OCRv4"}),
                ("PP-OCRv3", {"ocr_version": "PP-OCRv3"}),
                ("PP-OCRv5 (default)", {}),
            ]
            base_kwargs = dict(
                lang="en",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                # Use default recognition shape [3, 48, 320].
                # For long circuit lists (e.g. UL1-4,8,10,12,14,16,18),
                # use --dpi 300 on the CLI so each character is larger and
                # fits within the recognition window.
            )
            for label, extra_kwargs in variants:
                try:
                    logger.debug("Trying PaddleOCR 3.x with %s …", label)
                    eng = PaddleOCR(**base_kwargs, **extra_kwargs)
                    _paddle_smoke_test(eng)
                    logger.info("PaddleOCR 3.x initialised OK with %s (CPU)", label)
                    return eng, ver
                except Exception as exc:
                    logger.debug("  %s failed: %s: %s", label, type(exc).__name__, exc)
                    continue
            logger.warning(
                "All PaddleOCR 3.x model variants failed on this platform. "
                "This is a known PaddlePaddle oneDNN/PIR issue on Windows/Python 3.13. "
                "Falling back to EasyOCR. "
                "To use PaddleOCR, run on Linux or inside WSL2."
            )
            return None, 0

        else:
            # PaddleOCR 2.x legacy API
            eng = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False)
            _paddle_smoke_test(eng)
            logger.info("PaddleOCR 2.x initialised OK (CPU)")
            return eng, ver

    except ImportError:
        logger.debug("PaddleOCR not installed — skipping.")
        return None, 0
    except Exception as exc:
        logger.warning("PaddleOCR init failed: %s: %s", type(exc).__name__, exc)
        return None, 0


# ---------------------------------------------------------------------------
# EasyOCR initialisation
# ---------------------------------------------------------------------------

def _init_easyocr():
    import easyocr
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    logger.info("EasyOCR engine initialised (CPU)")
    return reader


# ---------------------------------------------------------------------------
# Engine selection
# ---------------------------------------------------------------------------

def _ensure_engine() -> None:
    global _backend, _paddle_engine, _easyocr_reader

    # Already initialised — fast return
    if _backend == "paddle"  and _paddle_engine   is not None:
        return
    if _backend == "easyocr" and _easyocr_reader   is not None:
        return

    # Forced backend not yet initialised
    if _backend == "paddle":
        eng, ver = _try_init_paddle()
        if eng is None:
            raise RuntimeError(
                "PaddleOCR could not be initialised on this platform. "
                "Use --ocr-backend easyocr or --ocr-backend auto instead."
            )
        _paddle_engine = (eng, ver)
        return

    if _backend == "easyocr":
        _easyocr_reader = _init_easyocr()
        return

    # Auto-detect: paddle first, EasyOCR fallback
    eng, ver = _try_init_paddle()
    if eng is not None:
        _paddle_engine = (eng, ver)
        _backend = "paddle"
    else:
        _easyocr_reader = _init_easyocr()
        _backend = "easyocr"


# ---------------------------------------------------------------------------
# Result parsers
# ---------------------------------------------------------------------------

def _parse_paddle_v2(result) -> list[dict]:
    """PaddleOCR 2.x result: [[ [polygon, (text, conf)], ... ]]"""
    tokens = []
    if not result or result[0] is None:
        return tokens
    for line in result[0]:
        if line is None:
            continue
        poly, (text, conf) = line
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        tokens.append({"text": text, "bbox": [min(xs), min(ys), max(xs), max(ys)], "conf": float(conf)})
    return tokens


def _parse_paddle_v3(result) -> list[dict]:
    """
    PaddleOCR 3.x result parser.

    PaddleOCR 3.x (via PaddleX) returns a list of dict-like objects with keys:
      "rec_texts"  — list of recognised strings
      "rec_scores" — list of confidence floats
      "rec_polys"  — list of (4, 2) int16 polygons  [KEY is rec_polys, NOT dt_polys]

    Each item supports dict-style access (item["rec_texts"]) NOT attribute access
    (item.rec_texts fails — confirmed by debug inspection).
    """
    tokens = []
    if not result:
        return tokens
    for item in result:
        if item is None:
            continue
        # PaddleOCR 3.x: dict-like object (has .get / .keys / .items)
        if hasattr(item, "get"):
            rec_texts  = item.get("rec_texts",  []) or []
            rec_scores = item.get("rec_scores", []) or []
            rec_polys  = item.get("rec_polys",  []) or []  # key is rec_polys, not dt_polys
            for poly, text, conf in zip(rec_polys, rec_texts, rec_scores):
                xs = [int(p[0]) for p in poly]
                ys = [int(p[1]) for p in poly]
                tokens.append({
                    "text":  text,
                    "bbox":  [min(xs), min(ys), max(xs), max(ys)],
                    "conf":  float(conf),
                })
        elif hasattr(item, "rec_texts"):        # future-proof object-style fallback
            rec_polys = getattr(item, "rec_polys", None) or getattr(item, "dt_polys", [])
            for poly, text, conf in zip(rec_polys, item.rec_texts, item.rec_scores):
                xs = [int(p[0]) for p in poly]
                ys = [int(p[1]) for p in poly]
                tokens.append({"text": text, "bbox": [min(xs), min(ys), max(xs), max(ys)], "conf": float(conf)})
        elif isinstance(item, list):            # PaddleOCR 2.x / legacy list
            tokens.extend(_parse_paddle_v2([item]))
    return tokens


def _parse_easyocr(result) -> list[dict]:
    """EasyOCR result: [(polygon, text, confidence), ...]"""
    tokens = []
    for poly, text, conf in result:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        tokens.append({"text": text, "bbox": [min(xs), min(ys), max(xs), max(ys)], "conf": float(conf)})
    return tokens


# ---------------------------------------------------------------------------
# Public OCR call
# ---------------------------------------------------------------------------

def run_ocr_on_tile(img: np.ndarray) -> list[dict]:
    """
    Run OCR on a single tile image (3-channel uint8 RGB/BGR).
    Returns list of dicts: {"text": str, "bbox": [x1, y1, x2, y2], "conf": float}
    """
    global _paddle_engine, _easyocr_reader

    _ensure_engine()

    try:
        if _backend == "paddle":
            eng, ver = _paddle_engine
            raw = eng.ocr(img)
            return _parse_paddle_v3(raw) if ver >= 3 else _parse_paddle_v2(raw)

        if _backend == "easyocr":
            if _easyocr_reader is None:
                _easyocr_reader = _init_easyocr()
            raw = _easyocr_reader.readtext(img)
            return _parse_easyocr(raw)

    except Exception as exc:
        logger.warning("OCR tile failed (backend=%s): %s", _backend, exc)

    return []
