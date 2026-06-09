"""
Debug why UL1-4,8,10,12,14,16,18 truncates but EL2-2,4,6,8,10,12,14,20,27,29 does not.
Renders a small region of the drawing and shows ALL OCR tokens with bounding boxes.
"""
import sys, warnings, os, logging
sys.path.insert(0, ".")
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.WARNING)

import fitz
import numpy as np
import cv2
from pipeline.preprocessor import preprocess_tile_for_paddle
from pipeline.ocr_engine import _try_init_paddle

PDF = ("input/Sample Project - AcxelInLabs (5599)"
       "_POWER_AND_SIGNAL_PLAN_-_LEVEL_8_SECTOR_1_E2.8.1_V1_04_28_2026.pdf")

eng, ver = _try_init_paddle()
doc = fitz.open(PDF)
page = doc[0]

for dpi in [200, 300]:
    zoom = dpi / 72.0
    pix  = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
    img  = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).copy()
    bgr  = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    result = eng.ocr(bgr)
    if not result:
        continue
    item = result[0]
    if not hasattr(item, "get"):
        continue

    texts  = item.get("rec_texts", [])
    scores = item.get("rec_scores", [])
    polys  = item.get("rec_polys", [])

    # Find tokens that look like UL1 or EL2 panel labels
    print(f"\n{'='*70}")
    print(f"DPI={dpi}  image size: {bgr.shape[1]}x{bgr.shape[0]}")
    print(f"Total OCR tokens: {len(texts)}")
    print(f"{'='*70}")
    print(f"{'Text':<35} {'Conf':>5}  {'x1':>5} {'y1':>5} {'x2':>5} {'y2':>5}  {'W':>5}")

    for txt, conf, poly in sorted(zip(texts, scores, polys), key=lambda x: (int(x[2][0][1]), int(x[2][0][0]))):
        # Show tokens that contain UL, EL, L8, LE or are purely digit/comma strings
        show = any(kw in txt.upper() for kw in ["UL", "EL", "L8", "LE", "U-", "E-", "L2-"])
        if not show and not all(c in "0123456789,." for c in txt):
            continue
        xs = [int(p[0]) for p in poly]
        ys = [int(p[1]) for p in poly]
        x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
        w = x2 - x1
        h = y2 - y1
        flag = " <-- TRUNCATED?" if len(txt) >= 12 and txt[-1].isdigit() and "," in txt else ""
        print(f"{txt:<35} {conf:>5.2f}  {x1:>5} {y1:>5} {x2:>5} {y2:>5}  {w:>5}  h={h}{flag}")

doc.close()
