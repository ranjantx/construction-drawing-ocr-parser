"""Quick validation: PaddleOCR produces tokens on a real PDF tile."""
import sys, warnings, logging
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

import cv2
import numpy as np
import fitz

from pipeline.preprocessor import preprocess_tile_for_paddle, preprocess_tile_for_easyocr
from pipeline.ocr_engine import set_backend, run_ocr_on_tile

PDF = ("input/Sample Project - AcxelInLabs (5599)"
       "_POWER_AND_SIGNAL_PLAN_-_LEVEL_8_SECTOR_1_E2.8.1_V1_04_28_2026.pdf")

# Render a small region at 150 DPI
doc = fitz.open(PDF)
page = doc[0]
zoom = 150 / 72.0
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).copy()
doc.close()

h, w = img.shape[:2]
# Crop a 800×600 tile from the centre of the drawing (likely to contain panel labels)
tile = img[h // 3 : h // 3 + 600, w // 3 : w // 3 + 800]
print(f"Test tile shape: {tile.shape}")

# --- PaddleOCR ---
paddle_img = preprocess_tile_for_paddle(tile)
print(f"\nPaddle preprocessed: shape={paddle_img.shape}  "
      f"dtype={paddle_img.dtype}  min={paddle_img.min()}  max={paddle_img.max()}")
set_backend("paddle")
results_paddle = run_ocr_on_tile(paddle_img)
print(f"PaddleOCR tokens: {len(results_paddle)}")
for r in results_paddle[:10]:
    print(f"  [{r['conf']:.2f}] {r['text']!r}")

# --- EasyOCR (for comparison) ---
easy_img = preprocess_tile_for_easyocr(tile)
print(f"\nEasyOCR preprocessed: shape={easy_img.shape}  "
      f"dtype={easy_img.dtype}  min={easy_img.min()}  max={easy_img.max()}")
set_backend("easyocr")
results_easy = run_ocr_on_tile(easy_img)
print(f"EasyOCR tokens: {len(results_easy)}")
for r in results_easy[:10]:
    print(f"  [{r['conf']:.2f}] {r['text']!r}")
