"""
Diagnose why long circuit lists like UL1-4,8,10,12,14,16,18 are truncated.
Tests 4 hypotheses on a real PDF tile.
"""
import sys, warnings, os
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"

import cv2, numpy as np, fitz
from pipeline.preprocessor import preprocess_tile_for_paddle
from pipeline.ocr_engine import _try_init_paddle

PDF = ("input/Sample Project - AcxelInLabs (5599)"
       "_POWER_AND_SIGNAL_PLAN_-_LEVEL_8_SECTOR_1_E2.8.1_V1_04_28_2026.pdf")

def ocr_tile(eng, img_bgr, label=""):
    result = eng.ocr(img_bgr)
    tokens = []
    if result:
        item = result[0]
        if hasattr(item, "get"):
            for txt, conf, poly in zip(
                item.get("rec_texts", []),
                item.get("rec_scores", []),
                item.get("rec_polys", []),
            ):
                xs = [int(p[0]) for p in poly]
                ys = [int(p[1]) for p in poly]
                w = max(xs) - min(xs)
                tokens.append((txt, conf, w, min(ys), max(ys)))
    print(f"\n{'='*60}")
    print(f"  {label}  ->  {len(tokens)} tokens")
    print(f"{'='*60}")
    for txt, conf, w, y1, y2 in sorted(tokens, key=lambda x: x[3]):
        h = y2 - y1
        print(f"  h={h:3d}px  w={w:4d}px  conf={conf:.2f}  {txt!r}")
    return tokens

eng, ver = _try_init_paddle()
print(f"Engine: PaddleOCR v{ver}")

doc = fitz.open(PDF)
page = doc[0]

for dpi in [200, 300, 400]:
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom),
                          colorspace=fitz.csRGB, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, 3).copy()
    h, w = img.shape[:2]
    # Crop a 1200x1200 tile from upper-right area (likely has panel labels)
    tile_raw = img[0:1200, w-1400:w-200]
    tile_bgr = cv2.cvtColor(tile_raw, cv2.COLOR_RGB2BGR)
    toks = ocr_tile(eng, tile_bgr, f"DPI={dpi}  tile_shape={tile_bgr.shape}")

    # Show any token wider than 120px (long text)
    long = [(t, c, ww) for t, c, ww, _, _ in toks if ww > 120]
    if long:
        print(f"  >> Long tokens (w>120px): {[(t,c) for t,c,_ in long]}")

doc.close()
