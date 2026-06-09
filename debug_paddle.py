"""Deep-dive: what does PaddleOCR 3.x actually return?"""
import sys, warnings, logging
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")

import cv2
import numpy as np
import fitz

from pipeline.preprocessor import preprocess_tile_for_paddle

PDF = ("input/Sample Project - AcxelInLabs (5599)"
       "_POWER_AND_SIGNAL_PLAN_-_LEVEL_8_SECTOR_1_E2.8.1_V1_04_28_2026.pdf")

# Render at 300 DPI for better text size
doc = fitz.open(PDF)
page = doc[0]
pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72), colorspace=fitz.csRGB, alpha=False)
img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).copy()
doc.close()

h, w = img.shape[:2]
tile_raw  = img[h//3:h//3+600, w//3:w//3+800]   # raw RGB
tile_bgr  = preprocess_tile_for_paddle(tile_raw)  # processed BGR
tile_orig_bgr = cv2.cvtColor(tile_raw, cv2.COLOR_RGB2BGR)  # raw BGR, no preprocessing

print(f"tile_raw shape:  {tile_raw.shape}")
print(f"tile_bgr shape:  {tile_bgr.shape}")

# Save tiles for visual inspection
cv2.imwrite("debug_tile_raw_bgr.png", tile_orig_bgr)
cv2.imwrite("debug_tile_processed_bgr.png", tile_bgr)
print("Saved debug_tile_raw_bgr.png and debug_tile_processed_bgr.png")

# Init PaddleOCR
import os
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
from paddleocr import PaddleOCR

eng = PaddleOCR(
    lang="en",
    ocr_version="PP-OCRv4",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)

print("\n--- Test 1: raw BGR (no preprocessing) ---")
result = eng.ocr(tile_orig_bgr)
print(f"Result type: {type(result)}")
print(f"Result len: {len(result) if result else 0}")
if result:
    r0 = result[0]
    print(f"result[0] type: {type(r0)}")
    print(f"result[0] attrs: {[a for a in dir(r0) if not a.startswith('_')]}")
    if hasattr(r0, "rec_texts"):
        print(f"rec_texts: {r0.rec_texts[:5]}")
        print(f"rec_scores: {r0.rec_scores[:5]}")
    elif hasattr(r0, "boxes"):
        print(f"boxes: {r0.boxes[:3]}")
    else:
        print(f"result[0] value: {r0}")

print("\n--- Test 2: processed BGR ---")
result2 = eng.ocr(tile_bgr)
print(f"Result type: {type(result2)}, len: {len(result2) if result2 else 0}")
if result2 and result2[0] is not None:
    r0 = result2[0]
    if hasattr(r0, "rec_texts"):
        print(f"Tokens found: {len(r0.rec_texts)}")
        for t, s in zip(r0.rec_texts[:10], r0.rec_scores[:10]):
            print(f"  [{s:.2f}] {t!r}")

print("\n--- Test 3: .predict() API ---")
try:
    result3 = eng.predict(tile_orig_bgr)
    print(f".predict() result type: {type(result3)}, len: {len(result3) if result3 else 0}")
    if result3:
        r0 = result3[0]
        print(f"result[0] attrs: {[a for a in dir(r0) if not a.startswith('_')][:15]}")
        if hasattr(r0, "rec_texts"):
            print(f"rec_texts: {r0.rec_texts[:10]}")
except Exception as e:
    print(f".predict() error: {e}")
