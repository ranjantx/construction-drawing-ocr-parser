from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    # PDF rendering
    dpi: int = 400
    dpi_min: int = 300
    dpi_max: int = 600

    # Tiling
    tile_size: int = 1200        # pixels per tile side
    tile_overlap: int = 300      # pixel overlap between adjacent tiles (increased from 200 for fragment recovery)

    # Circuit validation
    circuit_min: int = 1
    circuit_max: int = 84

    # IOU deduplication
    iou_threshold: float = 0.5

    # Geometry association
    proximity_factor: float = 3.0   # max N × panel_height for nearby search
    horizontal_align_factor: float = 1.5  # max N × panel_width for below check
    vertical_align_factor: float = 1.0    # max N × panel_height for right-of check

    # Panel schedule discovery (points in PDF space)
    panel_schedule_search_radius: float = 300.0

    # Confidence thresholds
    conf_high: float = 0.85
    conf_medium: float = 0.60
    conf_low: float = 0.40

    # Confidence weights
    weight_regex: float = 0.40
    weight_known_panel: float = 0.25
    weight_ocr_conf: float = 0.20
    weight_geometry: float = 0.15

    # OCR low-confidence threshold for human review flag
    ocr_conf_review_threshold: float = 0.70

    # Panel schedule keyword list
    panel_schedule_keywords: tuple = field(
        default=("PANEL SCHEDULE", "CIRCUIT DIRECTORY", "PANELBOARD", "PANEL BOARD")
    )


# Module-level singleton
CFG = Config()
