"""
CLI entry point for the electrical panel circuit extractor.

Usage:
  python extract_circuits.py --pdf input.pdf --output output/
  python extract_circuits.py --pdf input.pdf --output output/ --dpi 200 --ocr-backend easyocr --verbose
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path

from config import CFG

# Warn when a single page would produce more than this many tiles
_TILE_COUNT_WARNING = 60
# At 400 DPI an E-size sheet is ~12000×16800 → 204 tiles. Recommend 200 DPI.
_RECOMMENDED_DPI_FOR_LARGE_PAGES = 200


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )


def _load_panel_list(path: str | None) -> set[str]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        logging.warning("Panel list file not found: %s", path)
        return set()
    panels = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip().upper()
        if line:
            panels.add(line)
    logging.info("Loaded %d panels from %s", len(panels), path)
    return panels


def _estimate_tile_count(h: int, w: int, tile_size: int, overlap: int) -> int:
    step = tile_size - overlap
    rows = math.ceil(h / step)
    cols = math.ceil(w / step)
    return rows * cols


def run_pipeline(
    pdf_path: str,
    output_dir: str,
    dpi: int = CFG.dpi,
    extra_panels: set[str] | None = None,
    ocr_backend: str = "auto",
) -> None:
    try:
        from tqdm import tqdm
        _has_tqdm = True
    except ImportError:
        _has_tqdm = False

    from models.data_models import ExtractionResult
    from pipeline.classifier import classify_all
    from pipeline.confidence_scorer import score_all
    from pipeline.coordinate_mapper import make_ocr_token
    from pipeline.deduplicator import deduplicate_tokens
    from pipeline.geometry_analyzer import find_geometry_matches
    from pipeline.normalizer import normalize_text
    from pipeline.ocr_engine import run_ocr_on_tile, set_backend, get_requested_backend, get_engine
    set_backend(ocr_backend)
    from pipeline.output_writer import write_outputs
    from pipeline.fragment_recovery import recover_missing_fragments
    from pipeline.incomplete_panel_recovery import recover_truncated_panels
    from pipeline.panel_pattern_recognizer import PanelPatternRecognizer
    from pipeline.panel_validator import discover_known_panels
    from pipeline.pdf_renderer import iter_pages
    from pipeline.preprocessor import preprocess_tile
    from pipeline.text_merger import join_circuit_continuations
    from pipeline.tiler import tile_image
    from pipeline.zone_masker import detect_all_zones

    logger = logging.getLogger(__name__)
    logger.info("Starting extraction: %s", pdf_path)

    # Step 1a: Discover known panels from PDF text layer (panel schedules)
    known_panels = discover_known_panels(pdf_path)
    if extra_panels:
        known_panels |= extra_panels
    logger.info("Known panels: %s", sorted(known_panels) if known_panels else "(none — panel schedule not found in PDF)")

    # Step 1b: Detect drawing zones to mask before OCR (title block, notes, etc.)
    logger.info("Detecting drawing zones to exclude from OCR ...")
    page_zones = detect_all_zones(pdf_path)
    for pidx, zones in page_zones.items():
        logger.info(
            "  Page %d: %d zones masked (%.1f%% of page area excluded)",
            pidx, len(zones.zones), zones.coverage_fraction() * 100,
        )

    all_tokens = []
    page_count = 0

    # Step 2: Iterate pages → apply zone masks → tiles → OCR
    for page_idx, page_img in iter_pages(pdf_path, dpi=dpi, mask_title=False):
        # mask_title=False because zone_masker now handles the title block
        # (more precisely, with keyword confirmation)
        page_count += 1
        h, w = page_img.shape[:2]

        # Apply zone masks to white-out title block, notes, headers
        if page_idx in page_zones:
            page_img = page_zones[page_idx].apply_to_image(page_img, dpi)

        # Estimate tile count and warn if the image is very large
        n_tiles = _estimate_tile_count(h, w, CFG.tile_size, CFG.tile_overlap)
        if n_tiles > _TILE_COUNT_WARNING:
            logger.warning(
                "Page %d is large (%dx%d px at %d DPI) → %d tiles. "
                "EasyOCR on CPU takes ~2-4s/tile ≈ %.0f–%.0f minutes. "
                "Tip: re-run with --dpi %d for ~%d tiles (~2-4 min).",
                page_idx, w, h, dpi, n_tiles,
                n_tiles * 2 / 60, n_tiles * 4 / 60,
                _RECOMMENDED_DPI_FOR_LARGE_PAGES,
                _estimate_tile_count(
                    int(h * _RECOMMENDED_DPI_FOR_LARGE_PAGES / dpi),
                    int(w * _RECOMMENDED_DPI_FOR_LARGE_PAGES / dpi),
                    CFG.tile_size, CFG.tile_overlap,
                ),
            )
        else:
            logger.info("Page %d: %dx%d px → %d tiles", page_idx, w, h, n_tiles)

        page_tokens = []
        all_tiles = list(tile_image(page_img, page_index=page_idx))

        # Choose preprocessing pipeline based on OCR backend:
        #   paddle  → gray+CLAHE+sharpen, BGR (no binarisation — PaddleOCR
        #             detection needs gray-value gradients, not pure 0/255)
        #   easyocr → gray+CLAHE+adaptive-threshold, RGB (binary is fine for CRAFT)
        active_backend = get_requested_backend()
        preprocess_backend = "paddle" if active_backend == "paddle" else "easyocr"
        logger.debug("Using %s preprocessing pipeline for tiles", preprocess_backend)

        # Progress bar over tiles
        if _has_tqdm:
            tile_iter = tqdm(
                all_tiles,
                desc=f"Page {page_idx} OCR [{preprocess_backend}]",
                unit="tile",
                ncols=80,
                dynamic_ncols=True,
            )
        else:
            tile_iter = all_tiles

        for i, tile in enumerate(tile_iter):
            processed = preprocess_tile(tile.image, backend=preprocess_backend)
            raw_results = run_ocr_on_tile(processed)

            for ocr_result in raw_results:
                token = make_ocr_token(tile, ocr_result)
                token.normalized_text = normalize_text(token.raw_text, known_panels)
                page_tokens.append(token)

            # Fallback progress log every 10 tiles when tqdm not available
            if not _has_tqdm and (i + 1) % 10 == 0:
                logger.info("  Tile %d/%d done (%d tokens so far)", i + 1, len(all_tiles), len(page_tokens))

        # Step 3: Deduplicate overlapping tokens per page
        page_tokens = deduplicate_tokens(page_tokens)
        all_tokens.extend(page_tokens)
        logger.info("Page %d: %d tokens after deduplication", page_idx, len(page_tokens))

    logger.info("Total tokens extracted: %d", len(all_tokens))

    # Step 4: Classify all tokens (pass known_panels for quality gating)
    candidates = classify_all(all_tokens, known_panels=known_panels)

    # Step 5: Geometry pass — associate standalone panel+circuit pairs
    from pipeline.regex_patterns import looks_like_panel_label
    geo_matches = find_geometry_matches(all_tokens)
    geo_token_ids = {}
    for match in geo_matches:
        panel_text = match.panel_token.normalized_text
        if not looks_like_panel_label(panel_text, known_panels):
            continue
        panel_key = id(match.panel_token)
        geo_token_ids[panel_key] = match

    for candidate in candidates:
        tok_id = id(candidate.token)
        if tok_id in geo_token_ids:
            match = geo_token_ids[tok_id]
            candidate.classification = "panel_circuit"
            candidate.panel = match.panel_token.normalized_text
            candidate.circuit = match.circuit_token.normalized_text
            candidate.geometry_match = True
            candidate.reason = f"Geometry association ({match.relation}): {candidate.panel}-{candidate.circuit}"

    # Step 5b: Join split circuit-list continuations.
    # Fixes: panel_circuit(UL1, 4,8,10,12) + multi_circuit(14,16,18)
    #     → panel_circuit(UL1, 4,8,10,12,14,16,18)
    before_join = sum(1 for c in candidates if c.classification == "panel_circuit")
    candidates = join_circuit_continuations(candidates)
    after_join  = sum(1 for c in candidates if c.classification == "panel_circuit")
    if before_join != after_join:
        logger.info("Circuit continuations joined: %d panel_circuit tokens extended",
                    before_join - after_join)

    # Step 5b-recovery: Recover missed fragments using geometric association.
    # For fragments not detected by OCR: find nearest panel_circuit and append
    before_recovery = len([c for c in candidates if c.classification == "multi_circuit"])
    candidates = recover_missing_fragments(candidates)
    after_recovery = len([c for c in candidates if c.classification == "multi_circuit"])
    if before_recovery != after_recovery:
        logger.info("Fragment recovery: %d orphan fragments recovered via geometry",
                    before_recovery - after_recovery)

    # Step 5c-reocr: Re-OCR truncated panels to recover missing circuits.
    # Detects panels ending with comma/dash and re-OCR's adjacent areas for continuation
    # Builds page_images dict for re-OCR'ing
    page_images = {}
    for page_idx, page_img in iter_pages(pdf_path, dpi=dpi, mask_title=False):
        page_images[page_idx] = (page_img, page_img.shape[1], page_img.shape[0])

    ocr_engine = get_engine()
    before_reocr = sum(1 for c in candidates if c.classification == "panel_circuit")
    candidates = recover_truncated_panels(
        candidates,
        ocr_engine=ocr_engine,
        pdf_path=pdf_path,
        page_images=page_images,
        dpi=dpi,
    )
    after_reocr = sum(1 for c in candidates if c.classification == "panel_circuit")
    if before_reocr != after_reocr:
        logger.info("Truncated panel recovery: circuits extended via re-OCR")

    # Step 5d: Pattern recognizer — learn dominant panel naming convention
    # from THIS drawing's first-pass extractions, then use it to score labels.
    panel_recognizer = PanelPatternRecognizer()
    all_panel_labels = [c.panel for c in candidates
                        if c.classification == "panel_circuit" and c.panel]
    panel_recognizer.fit(all_panel_labels)
    logger.info(panel_recognizer.summary())

    # Step 6: Score all candidates (pass recognizer for pattern-quality boost)
    candidates = score_all(candidates, known_panels,
                           panel_recognizer=panel_recognizer)

    # Step 7: Build result and write outputs
    result = ExtractionResult(
        pdf_path=str(pdf_path),
        total_pages=page_count,
        candidates=candidates,
        known_panels=sorted(known_panels),
    )

    pc = result.panel_circuits
    logger.info(
        "Extraction complete: %d panel-circuit matches, %d rejected, %d need review",
        len(pc), len(result.rejected), len(result.needs_review),
    )

    write_outputs(result, output_dir)
    logger.info("Outputs written to: %s", output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract electrical panel labels and circuit numbers from a PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Tips for large E-size engineering drawings:
  --dpi 200   Recommended for most drawings (~48 tiles, ~2-4 min/page)
  --dpi 300   Higher accuracy at cost of longer runtime (~108 tiles)
  --dpi 400   Only if text is very small; slow on E-size sheets (~204 tiles)
""",
    )
    parser.add_argument("--pdf", required=True, help="Path to input PDF")
    parser.add_argument("--output", required=True, help="Output directory for JSON and Excel")
    parser.add_argument("--dpi", type=int, default=200,
                        help="Render DPI (default 200 — recommended for E-size sheets)")
    parser.add_argument("--panel-list", default=None,
                        help="Optional text file of known panel labels (one per line)")
    parser.add_argument("--ocr-backend", default="auto", choices=["auto", "paddle", "easyocr"],
                        help="OCR backend: auto (tries paddle then easyocr), paddle, or easyocr (default: auto)")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    extra_panels = _load_panel_list(args.panel_list)

    try:
        run_pipeline(
            pdf_path=str(pdf_path),
            output_dir=args.output,
            dpi=args.dpi,
            extra_panels=extra_panels,
            ocr_backend=args.ocr_backend,
        )
    except Exception:
        logging.exception("Fatal error during extraction")
        sys.exit(1)


if __name__ == "__main__":
    main()
