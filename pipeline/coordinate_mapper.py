"""
Map tile-local bounding boxes back to full-page pixel coordinates.
"""

from __future__ import annotations

from models.data_models import BBox, OCRToken
from pipeline.tiler import TileInfo


def tile_bbox_to_page(
    tile: TileInfo,
    bbox: list[float],  # [x1, y1, x2, y2] in tile-local pixels
) -> BBox:
    """Convert tile-local [x1,y1,x2,y2] to full-page BBox."""
    x1, y1, x2, y2 = bbox
    return BBox(
        x1=x1 + tile.offset_x,
        y1=y1 + tile.offset_y,
        x2=x2 + tile.offset_x,
        y2=y2 + tile.offset_y,
    )


def make_ocr_token(
    tile: TileInfo,
    ocr_result: dict,  # {"text", "bbox", "conf"}
) -> OCRToken:
    """Build an OCRToken from a raw OCR result dict, mapping coords to page space."""
    page_bbox = tile_bbox_to_page(tile, ocr_result["bbox"])
    return OCRToken(
        raw_text=ocr_result["text"],
        normalized_text=ocr_result["text"],
        ocr_confidence=ocr_result["conf"],
        bbox=page_bbox,
        page=tile.page,
        tile_id=tile.tile_id,
    )
