# Electrical Panel Circuit Extractor

Layout-aware extraction of electrical panel labels and circuit numbers from construction PDF drawings.

## Architecture

```
PDF → PyMuPDF (400–600 DPI)
    → Title-block masking
    → Overlapping tiles (1200px, 200px overlap)
    → OpenCV preprocessing (grayscale → CLAHE → adaptive threshold → optional deskew)
    → OCR engine (PaddleOCR preferred; EasyOCR auto-fallback on Windows/Python 3.13+)
    → Coordinate mapping (tile → page)
    → IOU deduplication
    → Text normalisation (dash variants, l→L, O/0 disambiguation)
    → Regex classification (9-step decision tree)
    → Geometry association (panel+circuit spatial pairing)
    → Panel schedule validation (native PDF text layer)
    → Confidence scoring (weighted: regex 0.40 + panel 0.25 + OCR 0.20 + geometry 0.15)
    → Excel (3 sheets) + JSON output
```

## Setup

### Requirements

- Python 3.11+ (3.13 supported)
- CPU-only (no GPU required)

### Install

```bash
cd parser
pip install -r requirements.txt
```

**OCR Backends** (the engine auto-detects which one works):

| Backend | Platform | Notes |
|---|---|---|
| EasyOCR | All (default) | Installs via pip, works on Python 3.13, Windows/Linux/Mac |
| PaddleOCR | Linux/Mac recommended | Better accuracy; on Windows+Python 3.13 has oneDNN issues |

To install PaddleOCR (Linux/Mac):
```bash
pip install paddlepaddle paddleocr
```

## Usage

### Basic

```bash
python extract_circuits.py --pdf "input/Sample Project - AcxelInLabs (5599)_LIGHTING_PLAN.pdf" --output output/
```

### With options

```bash
python extract_circuits.py \
  --pdf "input/Sample Project.pdf" \
  --output output/ \
  --dpi 500 \
  --panel-list known_panels.txt \
  --ocr-backend easyocr \
  --verbose
```

### Arguments

| Argument | Default | Description |
|---|---|---|
| `--pdf` | required | Path to input PDF |
| `--output` | required | Output directory |
| `--dpi` | 400 | Render resolution (300–600) |
| `--panel-list` | none | Text file of known panels (one per line) |
| `--ocr-backend` | auto | `auto` \| `paddle` \| `easyocr` |
| `--verbose` | false | Debug logging |

### known_panels.txt format

```
L1
LB1
P1
7LA
LL1B
```

## Outputs

Written to `<output>/circuits.xlsx` and `<output>/circuits.json`.

### Excel — Circuits sheet columns

| Column | Description |
|---|---|
| page | 0-based PDF page number |
| tile_id | Tile identifier (e.g. p0_r1_c2) |
| raw_text | Original OCR text |
| normalized_text | Normalised text (dashes, uppercase) |
| classification | panel_circuit / mounting_height / room_number / equipment_tag / fixture_device_tag / switch_leg / multi_circuit / unknown |
| panel | Panel label (e.g. L1, LB1) |
| circuit | Circuit number(s) (e.g. 5 or 29,31) |
| confidence | high / medium / low / reject |
| bbox_x1/y1/x2/y2 | Bounding box in page pixels |
| reason | Classification reasoning |
| needs_human_review | True if low confidence or uncertain |

### Excel sheets

- **Circuits** — All panel_circuit matches, colour-coded (green=high, yellow=medium, orange=low, red=reject)
- **Summary** — Pivot by panel: circuit counts + confidence breakdown
- **Rejected** — All rejected or human-review-flagged tokens

## Panel Label Rules

- Alphabetic or alphanumeric: `L1`, `P1`, `7LA`, `LB1`, `NL2A3`, `CRL2A2`, `4LF`, `LL1B`, `LA1`
- Must contain at least one letter

## Circuit Number Rules

- Whole integer, range **1–84 only**
- May be comma-separated: `1,3,5`
- Rejected if: contains letters (`47C`, `M25`), `> 84`, `0`, or unrelated annotation

## Classification Examples

| Input | Classification |
|---|---|
| `L1-5` | panel_circuit (panel=L1, circuit=5) |
| `7LA-29` | panel_circuit (panel=7LA, circuit=29) |
| `LB1 - 29,31` | panel_circuit (panel=LB1, circuit=29,31) |
| `+42"` | mounting_height |
| `112` | room_number |
| `300F-60` | equipment_tag |
| `FC-3` | equipment_tag |
| `B R012` | fixture_device_tag |
| `a`, `7b` | switch_leg |
| `45,47C` | reject (47C invalid) |

## Running Tests

```bash
pytest tests/ -v --cov=pipeline --cov-report=term-missing
```

### Test categories

- `test_regex.py` — ~40 parametrized regex cases
- `test_circuit_validation.py` — circuit range and rejection rules
- `test_classifier.py` — all 8 classification categories
- `test_geometry.py` — spatial association including LA1+1 pairing
- `test_integration.py` — full pipeline (place PDF in `tests/fixtures/`)
- `test_accuracy.py` — precision/recall against `tests/fixtures/ground_truth.json`

### Integration test setup

```bash
# Place your PDF in the fixtures directory
mkdir -p tests/fixtures
cp "your_drawing.pdf" tests/fixtures/sample_panel_labels.pdf

# Create ground truth (manually verified expected outputs)
# See tests/fixtures/ground_truth.json.example for format
pytest tests/test_integration.py tests/test_accuracy.py -v
```

### Ground truth format

```json
{
  "expected": [
    {"panel": "L1",  "circuit": "5"},
    {"panel": "LB1", "circuit": "29,31"},
    {"panel": "7LA", "circuit": "29"}
  ]
}
```

## Confidence Scoring

| Level | Score | Meaning |
|---|---|---|
| high | ≥ 0.85 | Regex + known panel + strong OCR |
| medium | ≥ 0.60 | Regex + valid circuit + good OCR |
| low | ≥ 0.40 | Geometry-only or low OCR confidence |
| reject | < 0.40 | Invalid circuit, failed validation, or unrelated |

Weights: regex (0.40) + known_panel (0.25) + OCR confidence (0.20) + geometry (0.15)

## Project Structure

```
parser/
├── extract_circuits.py     # CLI entry point
├── config.py               # Constants
├── requirements.txt
├── models/
│   └── data_models.py      # Pydantic: OCRToken, PanelCircuitCandidate, ExtractionResult
├── pipeline/
│   ├── pdf_renderer.py     # PyMuPDF page rendering + title block masking
│   ├── tiler.py            # Overlapping tile generation
│   ├── preprocessor.py     # OpenCV preprocessing
│   ├── ocr_engine.py       # PaddleOCR CPU wrapper
│   ├── coordinate_mapper.py
│   ├── deduplicator.py     # IOU-based NMS
│   ├── normalizer.py       # Text normalisation
│   ├── regex_patterns.py   # All compiled patterns
│   ├── geometry_analyzer.py
│   ├── classifier.py       # 9-step decision tree
│   ├── panel_validator.py  # Panel schedule discovery
│   ├── confidence_scorer.py
│   └── output_writer.py    # Excel + JSON
└── tests/
    ├── test_regex.py
    ├── test_circuit_validation.py
    ├── test_classifier.py
    ├── test_geometry.py
    ├── test_integration.py
    └── test_accuracy.py
```
