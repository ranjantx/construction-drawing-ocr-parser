"""
Split a page image into overlapping tiles.
Each tile tracks its top-left offset so coordinates can be mapped back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np

from config import CFG


@dataclass
class TileInfo:
    tile_id: str       # e.g. "p0_r0_c1"
    page: int
    row: int
    col: int
    offset_x: int      # pixel offset from left edge of full page
    offset_y: int      # pixel offset from top edge of full page
    image: np.ndarray  # tile pixel data (H×W×3)


def tile_image(
    page_img: np.ndarray,
    page_index: int,
    tile_size: int = CFG.tile_size,
    overlap: int = CFG.tile_overlap,
) -> Iterator[TileInfo]:
    """
    Yield TileInfo objects covering the full page with overlapping tiles.
    Edge tiles are zero-padded to maintain uniform tile_size × tile_size shape.
    """
    h, w = page_img.shape[:2]
    step = tile_size - overlap

    row = 0
    y = 0
    while y < h:
        col = 0
        x = 0
        while x < w:
            # Crop with clamping
            y2 = min(y + tile_size, h)
            x2 = min(x + tile_size, w)
            crop = page_img[y:y2, x:x2]

            # Zero-pad if the crop is smaller than tile_size
            tile_h, tile_w = crop.shape[:2]
            if tile_h < tile_size or tile_w < tile_size:
                padded = np.full((tile_size, tile_size, 3), 255, dtype=np.uint8)
                padded[:tile_h, :tile_w] = crop
                crop = padded

            yield TileInfo(
                tile_id=f"p{page_index}_r{row}_c{col}",
                page=page_index,
                row=row,
                col=col,
                offset_x=x,
                offset_y=y,
                image=crop,
            )

            col += 1
            x += step
            if x >= w:
                break

        row += 1
        y += step
        if y >= h:
            break
