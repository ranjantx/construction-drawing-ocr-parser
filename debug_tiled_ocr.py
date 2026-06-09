"""
Mimic the actual tiled pipeline to find which tile contains UL1 / EL2
and what OCR tokens are produced for them.
"""
import sys, warnings, os, logging
sys.path.insert(0, ".")
os.environ["FLAGS_use_mkldnn"] = "0"; os.environ["FLAGS_enable_pir_api"] = "0"
warnings.filterwarnings("ignore"); logging.basicConfig(level=logging.WARNING)

import fitz, numpy as np, cv2
from pipeline.tiler import tile_image
from pipeline.preprocessor import preprocess_tile_for_paddle
from pipeline.ocr_engine import _try_init_paddle
from pipeline.coordinate_mapper import make_ocr_token, tile_bbox_to_page
from pipeline.deduplicator import deduplicate_tokens
from pipeline.normalizer import normalize_text

PDF = ("input/Sample Project - AcxelInLabs (5599)"
       "_POWER_AND_SIGNAL_PLAN_-_LEVEL_8_SECTOR_1_E2.8.1_V1_04_28_2026.pdf")

eng, _ = _try_init_paddle()
doc = fitz.open(PDF)
page = doc[0]

for DPI in [200, 300]:
    zoom = DPI / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).copy()
    doc_h, doc_w = img.shape[:2]
    print(f"\n{'='*70}")
    print(f"DPI={DPI}  image={doc_w}x{doc_h}")

    all_tokens = []
    for tile in tile_image(img, page_index=0):
        processed = preprocess_tile_for_paddle(tile.image)
        result = eng.ocr(processed)
        if not result:
            continue
        item = result[0]
        if not hasattr(item, "get"):
            continue
        for txt, conf, poly in zip(item.get("rec_texts",[]), item.get("rec_scores",[]), item.get("rec_polys",[])):
            xs = [int(p[0]) for p in poly]; ys = [int(p[1]) for p in poly]
            raw_bbox = [min(xs), min(ys), max(xs), max(ys)]
            from models.data_models import BBox, OCRToken
            page_bbox = tile_bbox_to_page(tile, raw_bbox)
            tok = OCRToken(raw_text=txt, normalized_text=normalize_text(txt),
                           ocr_confidence=float(conf), bbox=page_bbox,
                           page=0, tile_id=tile.tile_id)
            all_tokens.append(tok)

    all_tokens = deduplicate_tokens(all_tokens)
    print(f"Total tokens after dedup: {len(all_tokens)}")

    # Find UL1, EL2 related tokens
    print(f"\n{'Normalised text':<35} {'Conf':>5}  {'x1':>6} {'y1':>6} {'x2':>6}  {'W':>5}")
    keywords = ["UL1", "EL2", "UL2", "EL1", "EL3", "L8N"]
    shown_lines = set()
    for t in sorted(all_tokens, key=lambda t: (t.bbox.center_y, t.bbox.x1)):
        txt_upper = t.normalized_text.upper()
        nearby_y = round(t.bbox.center_y / 10) * 10  # bucket by 10px
        # Show if it matches a keyword OR if it looks like a circuit list continuation
        is_continuation = all(c in "0123456789,." for c in t.raw_text) and "," in t.raw_text
        is_relevant = any(kw in txt_upper for kw in keywords) or is_continuation
        if not is_relevant:
            continue
        print(f"{t.normalized_text:<35} {t.ocr_confidence:>5.2f}  "
              f"{t.bbox.x1:>6.0f} {t.bbox.y1:>6.0f} {t.bbox.x2:>6.0f}  {t.bbox.width:>5.0f}")

doc.close()
