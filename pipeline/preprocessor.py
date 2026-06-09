"""
OpenCV preprocessing pipelines — two variants:

preprocess_tile_for_easyocr(img)
    Grayscale → CLAHE → adaptive binarisation → 3-ch RGB.
    EasyOCR's CRAFT detector is robust to pure binary images.

preprocess_tile_for_paddle(img)
    Grayscale → CLAHE → gentle unsharp-mask sharpening → 3-ch BGR.
    NO binarisation.  PaddleOCR's PP-OCR detection model is trained on
    natural/scanned documents; pure 0/255 binary images suppress gradient
    information that the detection head relies on and produce zero detections.
    BGR format is OpenCV-native and is what PaddleOCR expects internally.

preprocess_tile(img, backend)   ← convenience wrapper (default: easyocr)
"""

from __future__ import annotations

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return img.copy()


def apply_clahe(gray: np.ndarray, clip_limit: float = 2.0, grid: int = 8) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid, grid))
    return clahe.apply(gray)


def adaptive_threshold(gray: np.ndarray, block_size: int = 31, c: int = 10) -> np.ndarray:
    return cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size, c,
    )


def _unsharp_mask(gray: np.ndarray, sigma: float = 1.0, strength: float = 1.5) -> np.ndarray:
    """Sharpen edges without removing gray-value gradients."""
    blurred = cv2.GaussianBlur(gray, (0, 0), sigma)
    sharpened = cv2.addWeighted(gray, 1 + strength, blurred, -strength, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def _deskew_angle(binary: np.ndarray) -> float:
    edges = cv2.Canny(binary, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
    if lines is None:
        return 0.0
    angles = []
    for line in lines[:50]:
        rho, theta = line[0]
        angle_deg = np.degrees(theta) - 90
        if abs(angle_deg) < 10:
            angles.append(angle_deg)
    return float(np.median(angles)) if angles else 0.0


def deskew(gray: np.ndarray, binary: np.ndarray) -> np.ndarray:
    angle = _deskew_angle(binary)
    if abs(angle) < 0.5:
        return gray
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


# ---------------------------------------------------------------------------
# EasyOCR pipeline  (binary → RGB)
# ---------------------------------------------------------------------------

def preprocess_tile_for_easyocr(img: np.ndarray, do_deskew: bool = False) -> np.ndarray:
    """
    Full binarisation pipeline for EasyOCR.
    Returns 3-channel uint8 RGB — EasyOCR expects RGB/BGR, handles both.
    """
    gray = to_gray(img)
    enhanced = apply_clahe(gray)
    binary = adaptive_threshold(enhanced)
    if do_deskew:
        enhanced = deskew(enhanced, binary)
        binary = adaptive_threshold(enhanced)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)


# ---------------------------------------------------------------------------
# PaddleOCR pipeline  (gray-valued → BGR)
# ---------------------------------------------------------------------------

def preprocess_tile_for_paddle(img: np.ndarray, do_deskew: bool = False) -> np.ndarray:
    """
    Preprocessing for PaddleOCR.

    PaddleOCR PP-OCRv4 runs its own internal normalisation pipeline (mean/std
    normalisation, resize, etc.) — it works best on clean color or grayscale
    images in BGR format. Feeding it binarised images destroys the gradient
    information that the DBNet detection head relies on.

    Pipeline:
      1. RGB → BGR  (OpenCV / PaddleOCR native format)
      2. Optional mild CLAHE for contrast enhancement on low-contrast tiles
      3. Optional deskew (rare for construction PDFs)

    NO binarisation. NO unsharp mask. Keep it simple.
    """
    # Convert RGB (PyMuPDF output) → BGR (PaddleOCR / OpenCV native)
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    if do_deskew:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        binary = adaptive_threshold(apply_clahe(gray))
        angle = _deskew_angle(binary)
        if abs(angle) >= 0.5:
            h, w = bgr.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            bgr = cv2.warpAffine(bgr, M, (w, h), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)

    return bgr


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def preprocess_tile(img: np.ndarray, backend: str = "easyocr",
                    do_deskew: bool = False) -> np.ndarray:
    """
    Route to the correct preprocessing pipeline based on OCR backend.
    backend: "easyocr" | "paddle"
    """
    if backend == "paddle":
        return preprocess_tile_for_paddle(img, do_deskew=do_deskew)
    return preprocess_tile_for_easyocr(img, do_deskew=do_deskew)
