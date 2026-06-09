# Token Parser CLI — Usage Guide

**Date:** June 9, 2026  
**Tool:** token_parser.py  
**Purpose:** Parse and enrich electrical panel/circuit tokens from JSON/XLSX/CSV files

---

## Overview

The Token Parser CLI is a standalone tool that accepts extracted OCR tokens and enriches them with:

| Column | Description | Example |
|--------|-------------|---------|
| **normalized_text** | Standardized text (dash/case correction) | "L1-5" (from "L1—5") |
| **classification** | Token type classification | "panel_circuit", "equipment_tag", etc. |
| **panel** | Extracted panel label | "EL1", "UL1", "L2" |
| **circuit** | Extracted circuit number(s) | "25" or "2,4,6,8" |
| **confidence** | Confidence level | "HIGH", "MEDIUM", "LOW", "reject" |
| **reason** | Why classified/scored as such | "Regex match: PANEL_CIRCUIT_DASH" |
| **needs_human_review** | Requires manual verification | true/false |

---

## Installation

### Prerequisites
```bash
# Install base dependencies
pip install -r requirements.txt

# For Excel support
pip install openpyxl
```

### Check Installation
```bash
python token_parser.py --help
```

---

## Quick Start

### Basic Usage
```bash
# Parse JSON tokens
python token_parser.py --input tokens.json --output parsed.json

# Parse Excel file
python token_parser.py --input tokens.xlsx --output parsed.xlsx

# Parse CSV file
python token_parser.py --input tokens.csv --output parsed.csv
```

### With Options
```bash
# Specify DPI (for coordinate conversion)
python token_parser.py --input tokens.json --output parsed.json --dpi 300

# Enable verbose logging
python token_parser.py --input tokens.json --output parsed.json --verbose

# Specify known panels
python token_parser.py --input tokens.json --output parsed.json \
  --known-panels "EL1,EL2,EL3,UL1,UL2"
```

---

## Input Format

### Required Columns

Your input file **MUST** have these columns:

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `tile_id` | string | Unique tile identifier | "tile_0_0" |
| `raw_text` | string | OCR-extracted text | "L1-5" or "UL1-4,8,10,12" |
| `bbox_x1` | number | Left edge (PDF points) | 100.5 |
| `bbox_y1` | number | Top edge (PDF points) | 200.3 |
| `bbox_x2` | number | Right edge (PDF points) | 250.7 |
| `bbox_y2` | number | Bottom edge (PDF points) | 220.1 |

### Optional Columns

You can include additional columns, which will be preserved in output:

| Column | Type | Description |
|--------|------|-------------|
| `page` | integer | Page number (0-indexed) |
| `ocr_confidence` | float | OCR confidence 0.0-1.0 |
| `normalized_text` | string | Already-normalized text (will be overwritten) |
| [any other columns] | any | Preserved in output as-is |

### Example Input Formats

#### JSON Input
```json
[
  {
    "tile_id": "tile_0_0",
    "raw_text": "L1-5",
    "bbox_x1": 100.5,
    "bbox_y1": 200.3,
    "bbox_x2": 250.7,
    "bbox_y2": 220.1,
    "page": 0,
    "ocr_confidence": 0.95
  },
  {
    "tile_id": "tile_0_1",
    "raw_text": "UL1-4,8,10,12",
    "bbox_x1": 300.0,
    "bbox_y1": 150.0,
    "bbox_x2": 450.0,
    "bbox_y2": 170.0,
    "page": 0,
    "ocr_confidence": 0.92
  }
]
```

#### CSV Input
```csv
tile_id,raw_text,bbox_x1,bbox_y1,bbox_x2,bbox_y2,page,ocr_confidence
tile_0_0,L1-5,100.5,200.3,250.7,220.1,0,0.95
tile_0_1,UL1-4,300.0,150.0,450.0,170.0,0,0.92
tile_0_2,EL1-25,500.0,200.0,600.0,220.0,0,0.96
```

#### XLSX Input
| tile_id | raw_text | bbox_x1 | bbox_y1 | bbox_x2 | bbox_y2 | page | ocr_confidence |
|---------|----------|---------|---------|---------|---------|------|----------------|
| tile_0_0 | L1-5 | 100.5 | 200.3 | 250.7 | 220.1 | 0 | 0.95 |
| tile_0_1 | UL1-4,8,10,12 | 300.0 | 150.0 | 450.0 | 170.0 | 0 | 0.92 |

---

## Output Format

### Output Columns

Your output file will contain:

**Preserved columns** (from input):
- `tile_id`
- `page` (if present)
- `ocr_confidence` (if present)
- Any other custom columns from input

**Enriched columns** (added/updated):
- `raw_text` — Original OCR text
- `normalized_text` — Standardized text
- `classification` — Token type
- `panel` — Extracted panel label
- `circuit` — Extracted circuit(s)
- `confidence` — Confidence level
- `reason` — Classification rationale
- `needs_human_review` — Review flag

### Example Output

#### JSON Output
```json
[
  {
    "tile_id": "tile_0_0",
    "page": 0,
    "ocr_confidence": 0.95,
    "raw_text": "L1-5",
    "normalized_text": "L1-5",
    "classification": "panel_circuit",
    "panel": "L1",
    "circuit": "5",
    "confidence": "high",
    "reason": "Regex match: PANEL_CIRCUIT_DASH (L1-5)",
    "needs_human_review": false
  },
  {
    "tile_id": "tile_0_1",
    "page": 0,
    "ocr_confidence": 0.92,
    "raw_text": "UL1-4,8,10,12,14,16,18",
    "normalized_text": "UL1-4,8,10,12,14,16,18",
    "classification": "panel_circuit",
    "panel": "UL1",
    "circuit": "4,8,10,12,14,16,18",
    "confidence": "medium",
    "reason": "Regex match + OCR confidence boost",
    "needs_human_review": false
  }
]
```

#### CSV Output
```csv
tile_id,page,ocr_confidence,raw_text,normalized_text,classification,panel,circuit,confidence,reason,needs_human_review
tile_0_0,0,0.95,L1-5,L1-5,panel_circuit,L1,5,high,Regex match: PANEL_CIRCUIT_DASH (L1-5),False
tile_0_1,0,0.92,UL1-4,UL1-4,panel_circuit,UL1,4,medium,Regex match + OCR confidence boost,False
```

---

## Classification Types

The tool classifies each token into one of these categories:

### Electrical Panels (panel_circuit)
✅ **Classified as:** `panel_circuit`
- Pattern: `[A-Z][A-Z0-9]{0,7}` or `[0-9][A-Z][A-Z0-9]{0,6}` followed by `-` or `:` and circuit number(s)
- Examples:
  - "L1-5" → panel: L1, circuit: 5
  - "EL2-2,4,6,8" → panel: EL2, circuit: 2,4,6,8
  - "UL1-4,8,10,12" → panel: UL1, circuit: 4,8,10,12
  - "7LA-29" → panel: 7LA, circuit: 29

### Equipment Tags ❌
**Classified as:** `equipment_tag`
- Pattern: `[A-Z]{1,3}-[0-9]+[A-Z]?` or similar
- Examples: "FC-3", "EQ-10", "300F-60", "2D-06"
- ❌ NOT panel-circuit references

### Fixture/Device Tags ❌
**Classified as:** `fixture_device_tag`
- Pattern: `[A-Z0-9]{1,4}\s+R[0-9]{3,}`
- Examples: "B R012", "GX6 R012", "FIXTURE R001"
- ❌ NOT panel-circuit references

### Mounting Heights ❌
**Classified as:** `mounting_height`
- Pattern: `+[0-9]+[""'A-Z]*`
- Examples: "+42"", "+48AFF"
- ❌ NOT panel-circuit references

### Switch Legs ❌
**Classified as:** `switch_leg`
- Pattern: `[0-9]{0,2}[a-d](?:,[0-9]{0,2}[a-d])*`
- Examples: "a", "b", "7a", "7b", "2a,2b"
- ❌ NOT panel-circuit references

### Room Numbers ❌
**Classified as:** `room_number`
- Pattern: Single or multi-digit number > 84
- Examples: "112", "114", "205"
- ❌ NOT panel-circuit references

### Unknown/Unclassified
**Classified as:** `unknown`
- Could not be classified with confidence
- Requires human review

---

## Confidence Levels

Each token is assigned a confidence score:

| Level | Score | Meaning | Action |
|-------|-------|---------|--------|
| **HIGH** | ≥ 0.85 | Highly confident, correct classification | ✅ Use as-is |
| **MEDIUM** | 0.60-0.84 | Fairly confident, minor uncertainty | ⚠️ Review if needed |
| **LOW** | 0.40-0.59 | Low confidence, recommend review | 🔍 Manual review |
| **reject** | < 0.40 | Incorrect or invalid, reject | ❌ Skip/exclude |

### Confidence Calculation

```
confidence_score = 
    0.40 × regex_match_score +
    0.25 × known_panel_score +
    0.20 × ocr_confidence +
    0.15 × geometry_score
```

Where:
- **regex_match_score:** 1.0 if regex pattern matches, 0.5 if partial
- **known_panel_score:** 1.0 if panel in known_panels list, 0.0 otherwise
- **ocr_confidence:** OCR confidence from input (0.0-1.0)
- **geometry_score:** 0.65 if geometry-matched, 0.0 otherwise

---

## Known Panels

### What is `--known-panels`?

If you have a list of panel labels that you know exist in your facility, you can provide them to improve confidence scoring:

```bash
python token_parser.py --input tokens.json --output parsed.json \
  --known-panels "EL1,EL2,EL3,UL1,UL2,L1,L2,L3"
```

### Impact

Tokens matching known panels get a **+0.25 confidence boost**, increasing accuracy of high-confidence matches.

### Where to Get Known Panels

1. **From PDF Panel Schedule:** Extract panel list from facility electrical panel schedule
2. **From Previous Extraction:** Use panel list from previous successful extraction
3. **From Facility Records:** Use electrical drawing legend or panel list

---

## Examples

### Example 1: Basic JSON Parsing
```bash
# Input: tokens.json
python token_parser.py --input tokens.json --output parsed.json

# Output: parsed.json (same tokens + enriched columns)
```

### Example 2: Excel with Known Panels
```bash
# Input: Sheet1 with token columns
python token_parser.py \
  --input facility_tokens.xlsx \
  --output parsed_facility.xlsx \
  --known-panels "EL1,EL2,EL3,UL1,UL2" \
  --verbose

# Output: parsed_facility.xlsx with classification/scoring
```

### Example 3: CSV with Custom DPI
```bash
# Input: tokens.csv (coordinates at 400 DPI)
python token_parser.py \
  --input tokens.csv \
  --output parsed.csv \
  --dpi 400 \
  --verbose

# Output: parsed.csv with coordinate conversion
```

### Example 4: Batch Processing
```bash
#!/bin/bash
# Process multiple files

for input_file in input/*.json; do
  output_file="output/$(basename "$input_file" .json)_parsed.json"
  python token_parser.py --input "$input_file" --output "$output_file" \
    --known-panels "EL1,EL2,UL1,UL2" --verbose
done
```

---

## Error Handling

### Common Issues

#### Missing Required Columns
```
ERROR: Missing required columns: bbox_x1, bbox_y2
ERROR: Required columns: tile_id, raw_text, bbox_x1, bbox_y1, bbox_x2, bbox_y2
```

**Solution:** Ensure your input file has all required columns. Check the column names match exactly.

#### File Not Found
```
ERROR: Input file not found: tokens.json
```

**Solution:** Check file path is correct and file exists.

#### Invalid JSON
```
ERROR: Invalid JSON in tokens.json: Expecting value: line 1 column 1 (char 0)
```

**Solution:** Validate JSON syntax. Use online JSON validator if needed.

#### Unsupported Format
```
ERROR: Unsupported file format: .txt
Supported formats: .json, .xlsx, .csv
```

**Solution:** Convert file to JSON, XLSX, or CSV format.

#### Missing openpyxl
```
ERROR: openpyxl not installed. Install with: pip install openpyxl
```

**Solution:** Install openpyxl: `pip install openpyxl`

---

## Command-Line Options

### Required Arguments

```
--input FILE, -i FILE
    Input file (JSON/XLSX/CSV with tokens)
    REQUIRED
    Example: --input tokens.json
```

```
--output FILE, -o FILE
    Output file (same format as input)
    REQUIRED
    Example: --output parsed.json
```

### Optional Arguments

```
--dpi NUMBER
    DPI for PDF coordinate conversion
    Default: 300
    Example: --dpi 400
```

```
--known-panels PANELS
    Comma-separated list of known panel labels
    Default: (empty)
    Example: --known-panels "EL1,EL2,UL1"
```

```
--verbose, -v
    Enable debug logging
    Default: False
    Example: --verbose
```

```
--help, -h
    Show help message and exit
```

---

## Output Directory

The tool will automatically create the output directory if it doesn't exist:

```bash
# Creates "output/" directory if needed
python token_parser.py --input tokens.json --output output/parsed.json
```

---

## Logging

### Log Levels

- **INFO** (default): Key milestones and results
- **DEBUG** (--verbose): Detailed processing steps

### Sample Log Output
```
13:45:22 [INFO] Token Parser — Parse electrical panel/circuit tokens
═══════════════════════════════════════════════════════════════════════════════
13:45:22 [INFO] Input file: tokens.json
13:45:22 [INFO] Output file: parsed.json
13:45:22 [INFO] DPI: 300
13:45:22 [INFO] Reading input file...
13:45:22 [INFO] Loaded 150 tokens from tokens.json
13:45:22 [INFO] Validating columns...
13:45:22 [INFO] ✓ All required columns present: raw_text, tile_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2
13:45:22 [INFO] Converting to OCR tokens...
13:45:22 [INFO] Converted 150 tokens from 150 rows
13:45:22 [INFO] ─────────────────────────────────────────────────────────────────────────────────
13:45:22 [INFO] Enriching tokens (normalize, classify, score)...
13:45:22 [INFO] Step 1: Normalizing text...
13:45:22 [INFO] Step 2: Classifying tokens...
13:45:22 [INFO] Step 3: Scoring candidates...
13:45:22 [INFO] Converting to output format...
13:45:22 [INFO] Writing output file...
13:45:22 [INFO] Wrote 150 tokens to parsed.json
13:45:22 [INFO] ═══════════════════════════════════════════════════════════════════════════════════
13:45:22 [INFO] RESULTS SUMMARY
13:45:22 [INFO] ═══════════════════════════════════════════════════════════════════════════════════
13:45:22 [INFO] Total tokens processed: 150
13:45:22 [INFO] Panel-circuit matches: 105
13:45:22 [INFO]   HIGH confidence: 87
13:45:22 [INFO]   MEDIUM confidence: 18
13:45:22 [INFO]   LOW confidence: 5
13:45:22 [INFO]   REJECTED: 45
13:45:22 [INFO] Flagged for human review: 5
13:45:22 [INFO] ═══════════════════════════════════════════════════════════════════════════════════
13:45:22 [INFO] ✓ Output written to: parsed.json
```

---

## Integration Examples

### Python Integration
```python
from token_parser import _read_json, _validate_input_columns, \
    _convert_to_ocr_tokens, _enrich_tokens, _candidates_to_output_rows, _write_json

# Read tokens
input_rows = _read_json("tokens.json")

# Validate
_validate_input_columns(input_rows)

# Convert
tokens = _convert_to_ocr_tokens(input_rows, dpi=300)

# Enrich
candidates = _enrich_tokens(tokens, known_panels={"EL1", "EL2"})

# Convert back
output_rows = _candidates_to_output_rows(candidates, input_rows)

# Write
_write_json("parsed.json", output_rows)
```

### Shell Script Integration
```bash
#!/bin/bash
python token_parser.py \
  --input "$1" \
  --output "${1%.json}_parsed.json" \
  --known-panels "EL1,EL2,EL3,UL1" \
  --verbose
```

---

## FAQ

**Q: Can I process multiple files at once?**
A: Use a shell script or loop to call token_parser.py multiple times.

**Q: What if my coordinates are already in pixels, not PDF points?**
A: Set `--dpi 72` (the conversion factor) to disable coordinate scaling.

**Q: Can I filter the output (e.g., only HIGH confidence)?**
A: Post-process the output file using Python, Pandas, or Excel filtering.

**Q: Do I need to specify all optional columns?**
A: No, only `tile_id`, `raw_text`, and `bbox_*` are required. Other columns are optional.

**Q: Can I use `--known-panels` with a file instead of comma-separated list?**
A: Not directly, but you can modify token_parser.py to read from a file.

**Q: How long does it take to process N tokens?**
A: Typically 1-2ms per token (~150 tokens/sec on modern CPU).

---

## Summary

The Token Parser CLI is a production-ready tool for enriching OCR tokens with:

✅ Text normalization  
✅ Classification (panel, circuit, equipment, etc.)  
✅ Confidence scoring  
✅ Human review flagging  

**Supports:** JSON, XLSX, CSV  
**Required:** 6 input columns (tile_id, raw_text, bbox_x1, bbox_y1, bbox_x2, bbox_y2)  
**Output:** Same format + 7 enriched columns  

---

## Support

For issues, questions, or feature requests, please refer to:
- **Code:** `token_parser.py`
- **Examples:** See above examples section
- **Options:** `python token_parser.py --help`

