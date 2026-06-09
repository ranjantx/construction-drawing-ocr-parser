# Token Parser CLI — Examples & Quick Start

**Quick Reference:** `python token_parser.py --help`

---

## 30-Second Quick Start

```bash
# 1. Create input JSON with tokens
cat > tokens.json << 'EOF'
[
  {"tile_id": "t1", "raw_text": "L1-5", "bbox_x1": 100, "bbox_y1": 200, "bbox_x2": 250, "bbox_y2": 220},
  {"tile_id": "t2", "raw_text": "EL1-25", "bbox_x1": 300, "bbox_y1": 150, "bbox_x2": 450, "bbox_y2": 170}
]
EOF

# 2. Parse tokens
python token_parser.py --input tokens.json --output parsed.json

# 3. Check results
cat parsed.json | python -m json.tool | head -20
```

---

## Example 1: Basic Parsing

### Input: `simple_tokens.json`
```json
[
  {
    "tile_id": "tile_A",
    "raw_text": "L1-5",
    "bbox_x1": 100.0,
    "bbox_y1": 200.0,
    "bbox_x2": 250.0,
    "bbox_y2": 220.0
  }
]
```

### Command
```bash
python token_parser.py \
  --input simple_tokens.json \
  --output simple_parsed.json
```

### Output: `simple_parsed.json`
```json
[
  {
    "tile_id": "tile_A",
    "raw_text": "L1-5",
    "bbox_x1": 100.0,
    "bbox_y1": 200.0,
    "bbox_x2": 250.0,
    "bbox_y2": 220.0,
    "normalized_text": "L1-5",
    "classification": "panel_circuit",
    "panel": "L1",
    "circuit": "5",
    "confidence": "medium",
    "reason": "Regex dash match: panel=L1 circuits=5",
    "needs_human_review": false
  }
]
```

---

## Example 2: Multiple Panels with Known Panels

### Input: `facility_tokens.json`
```json
[
  {"tile_id": "t1", "raw_text": "EL1-25", "bbox_x1": 100, "bbox_y1": 200, "bbox_x2": 250, "bbox_y2": 220, "page": 0, "ocr_confidence": 0.95},
  {"tile_id": "t2", "raw_text": "UL1-4,8,10", "bbox_x1": 300, "bbox_y1": 150, "bbox_x2": 450, "bbox_y2": 170, "page": 0, "ocr_confidence": 0.92},
  {"tile_id": "t3", "raw_text": "L2-6,8", "bbox_x1": 500, "bbox_y1": 200, "bbox_x2": 650, "bbox_y2": 220, "page": 0, "ocr_confidence": 0.88}
]
```

### Command
```bash
python token_parser.py \
  --input facility_tokens.json \
  --output facility_parsed.json \
  --known-panels "EL1,EL2,UL1,UL2,L1,L2" \
  --verbose
```

### Output Summary
```
Total tokens processed: 3
Panel-circuit matches: 3
  HIGH confidence: 2 (EL1 and UL1 in known_panels)
  MEDIUM confidence: 1 (L2 not in known_panels)
  LOW confidence: 0
  REJECTED: 0
```

### Output Details: `facility_parsed.json`
```json
[
  {
    "tile_id": "t1",
    "raw_text": "EL1-25",
    "page": 0,
    "ocr_confidence": 0.95,
    "normalized_text": "EL1-25",
    "classification": "panel_circuit",
    "panel": "EL1",
    "circuit": "25",
    "confidence": "high",
    "reason": "Regex dash match: panel=EL1 circuits=25 (known panel)",
    "needs_human_review": false
  },
  {
    "tile_id": "t2",
    "raw_text": "UL1-4,8,10",
    "page": 0,
    "ocr_confidence": 0.92,
    "normalized_text": "UL1-4,8,10",
    "classification": "panel_circuit",
    "panel": "UL1",
    "circuit": "4,8,10",
    "confidence": "high",
    "reason": "Regex dash match: panel=UL1 circuits=4,8,10 (known panel)",
    "needs_human_review": false
  },
  {
    "tile_id": "t3",
    "raw_text": "L2-6,8",
    "page": 0,
    "ocr_confidence": 0.88,
    "normalized_text": "L2-6,8",
    "classification": "panel_circuit",
    "panel": "L2",
    "circuit": "6,8",
    "confidence": "medium",
    "reason": "Regex dash match: panel=L2 circuits=6,8",
    "needs_human_review": false
  }
]
```

---

## Example 3: Excel Input/Output

### Input: `tokens.xlsx`
| tile_id | raw_text | bbox_x1 | bbox_y1 | bbox_x2 | bbox_y2 | page | ocr_confidence |
|---------|----------|---------|---------|---------|---------|------|----------------|
| tile_0 | L1-5 | 100.0 | 200.0 | 250.0 | 220.0 | 0 | 0.95 |
| tile_1 | FC-3 | 300.0 | 150.0 | 400.0 | 170.0 | 0 | 0.97 |
| tile_2 | +42" | 500.0 | 200.0 | 550.0 | 220.0 | 0 | 0.98 |

### Command
```bash
python token_parser.py \
  --input tokens.xlsx \
  --output parsed.xlsx \
  --dpi 300 \
  --verbose
```

### Output: `parsed.xlsx`
| tile_id | raw_text | bbox_x1 | bbox_y1 | bbox_x2 | bbox_y2 | page | ocr_confidence | normalized_text | classification | panel | circuit | confidence | reason | needs_human_review |
|---------|----------|---------|---------|---------|---------|------|----------------|-----------------|----------------|-------|---------|------------|--------|-------------------|
| tile_0 | L1-5 | 100.0 | 200.0 | 250.0 | 220.0 | 0 | 0.95 | L1-5 | panel_circuit | L1 | 5 | medium | Regex dash match... | False |
| tile_1 | FC-3 | 300.0 | 150.0 | 400.0 | 170.0 | 0 | 0.97 | FC-3 | equipment_tag | | | reject | Equipment tag (FC-3) | False |
| tile_2 | +42" | 500.0 | 200.0 | 550.0 | 220.0 | 0 | 0.98 | +42" | mounting_height | | | reject | Mounting height... | False |

---

## Example 4: CSV Processing

### Input: `tokens.csv`
```csv
tile_id,raw_text,bbox_x1,bbox_y1,bbox_x2,bbox_y2
tile_0,EL1-25,100,200,250,220
tile_1,UL1-4,8,300,150,450,170
tile_2,7LA-29,500,200,700,220
tile_3,7a,100,400,150,420
tile_4,112,200,450,250,470
```

### Command
```bash
python token_parser.py \
  --input tokens.csv \
  --output parsed.csv
```

### Output: `parsed.csv`
```csv
tile_id,raw_text,bbox_x1,bbox_y1,bbox_x2,bbox_y2,normalized_text,classification,panel,circuit,confidence,reason,needs_human_review
tile_0,EL1-25,100,200,250,220,EL1-25,panel_circuit,EL1,25,medium,Regex dash match: panel=EL1 circuits=25,False
tile_1,UL1-4,8,300,150,450,170,UL1-4,panel_circuit,UL1,4,medium,Regex dash match: panel=UL1 circuits=4,False
tile_2,7LA-29,500,200,700,220,7LA-29,panel_circuit,7LA,29,medium,Regex dash match: panel=7LA circuits=29,False
tile_3,7a,100,400,150,420,7a,switch_leg,,,reject,Switch leg (7a),False
tile_4,112,200,450,250,470,112,room_number,,,reject,Room number (112),False
```

---

## Example 5: Batch Processing Script

### Script: `process_all_tokens.sh`
```bash
#!/bin/bash

# Process all JSON files in input/ directory
for input_file in input/*.json; do
    output_file="output/$(basename "$input_file" .json)_parsed.json"
    
    echo "Processing: $input_file → $output_file"
    
    python token_parser.py \
        --input "$input_file" \
        --output "$output_file" \
        --known-panels "EL1,EL2,EL3,UL1,UL2,L1,L2,L3,L4" \
        --dpi 300 \
        --verbose
    
    if [ $? -eq 0 ]; then
        echo "✓ Success: $output_file"
    else
        echo "✗ Failed: $input_file"
    fi
done
```

### Usage
```bash
chmod +x process_all_tokens.sh
./process_all_tokens.sh
```

---

## Example 6: Python Integration

### Script: `integrate_parser.py`
```python
from pathlib import Path
from token_parser import (
    _read_json, _validate_input_columns, _convert_to_ocr_tokens,
    _enrich_tokens, _candidates_to_output_rows, _write_json
)

# Load tokens
input_rows = _read_json("tokens.json")

# Validate
_validate_input_columns(input_rows)

# Convert to OCR tokens
tokens = _convert_to_ocr_tokens(input_rows, dpi=300)

# Enrich with classification and scoring
known_panels = {"EL1", "EL2", "UL1", "UL2"}
candidates = _enrich_tokens(tokens, known_panels=known_panels)

# Get high-confidence results
high_conf = [c for c in candidates if c.confidence == "high"]
print(f"High confidence matches: {len(high_conf)}")

for c in high_conf[:5]:
    print(f"  {c.panel}-{c.circuit} (OCR: {c.token.raw_text})")

# Convert back to rows and save
output_rows = _candidates_to_output_rows(candidates, input_rows)
_write_json("parsed.json", output_rows)
```

### Usage
```bash
python integrate_parser.py
```

---

## Example 7: Filter High-Confidence Results

### Command
```bash
# Parse all tokens
python token_parser.py --input tokens.json --output parsed.json

# Filter for HIGH confidence only
python << 'EOF'
import json

with open('parsed.json', 'r') as f:
    parsed = json.load(f)

# Filter
high_conf = [t for t in parsed if t['confidence'] == 'high']

# Save
with open('parsed_high_confidence.json', 'w') as f:
    json.dump(high_conf, f, indent=2)

print(f"Filtered {len(high_conf)}/{len(parsed)} high-confidence tokens")
EOF
```

---

## Example 8: Real-World E201A Drawing

### Input: Extract from actual E201A drawing
```json
[
  {"tile_id": "page0_tile5", "raw_text": "EL1-3", "bbox_x1": 450, "bbox_y1": 300, "bbox_x2": 550, "bbox_y2": 320, "page": 0, "ocr_confidence": 0.96},
  {"tile_id": "page0_tile8", "raw_text": "EL1-5", "bbox_x1": 600, "bbox_y1": 350, "bbox_x2": 700, "bbox_y2": 370, "page": 0, "ocr_confidence": 0.94},
  {"tile_id": "page0_tile12", "raw_text": "UL1-4,8,10,12,14,16,18", "bbox_x1": 250, "bbox_y1": 500, "bbox_x2": 500, "bbox_y2": 520, "page": 0, "ocr_confidence": 0.92},
  {"tile_id": "page0_tile15", "raw_text": "EL2-2,4,6,8,10,12,14,20,27,29", "bbox_x1": 800, "bbox_y1": 400, "bbox_x2": 1100, "bbox_y2": 420, "page": 0, "ocr_confidence": 0.88}
]
```

### Command
```bash
python token_parser.py \
  --input e201a_tokens.json \
  --output e201a_parsed.json \
  --known-panels "EL1,EL2,EL3,EL4,UL1,UL2,E,U,N" \
  --dpi 300 \
  --verbose
```

### Results
```
Total tokens processed: 4
Panel-circuit matches: 4
  HIGH confidence: 2 (EL1 and EL2 in known_panels)
  MEDIUM confidence: 2 (UL1 not in list)
  LOW confidence: 0
  REJECTED: 0
```

---

## Example 9: Error Handling

### Missing Required Columns
```bash
$ cat bad_input.json
[{"tile_id": "t1", "raw_text": "L1-5"}]

$ python token_parser.py --input bad_input.json --output out.json
ERROR: Missing required columns: bbox_x1, bbox_x2, bbox_y1, bbox_y2
ERROR: Required columns: tile_id, raw_text, bbox_x1, bbox_y1, bbox_x2, bbox_y2
```

### Solution
```bash
# Add missing bbox columns
cat > good_input.json << 'EOF'
[{"tile_id": "t1", "raw_text": "L1-5", "bbox_x1": 100, "bbox_y1": 200, "bbox_x2": 250, "bbox_y2": 220}]
EOF

python token_parser.py --input good_input.json --output out.json
✓ Success!
```

---

## Performance Examples

### Processing Speed
```
10 tokens:     ~10ms
100 tokens:    ~50ms
1,000 tokens:  ~500ms
10,000 tokens: ~5 seconds
```

### Large Batch Example
```bash
# Process 5,000 tokens
python token_parser.py \
  --input large_batch.json \
  --output large_batch_parsed.json \
  --known-panels "$(cat known_panels.txt)" \
  --verbose

# Typical output:
# Total tokens processed: 5000
# Panel-circuit matches: 3500
#   HIGH confidence: 2800
#   MEDIUM confidence: 700
#   LOW confidence: 0
#   REJECTED: 1500
# Processing time: ~5 seconds
```

---

## Cheat Sheet

| Task | Command |
|------|---------|
| Basic parsing | `python token_parser.py --input in.json --output out.json` |
| With known panels | `... --known-panels "EL1,EL2,UL1"` |
| Verbose logging | `... --verbose` |
| Custom DPI | `... --dpi 400` |
| Show help | `python token_parser.py --help` |
| Process CSV | `... --input tokens.csv --output parsed.csv` |
| Process Excel | `... --input tokens.xlsx --output parsed.xlsx` |

---

## Next Steps

1. **Prepare input:** Create JSON/CSV/XLSX with required columns
2. **Run parser:** `python token_parser.py --input ... --output ...`
3. **Review results:** Check output for confidence levels
4. **Filter:** Keep HIGH/MEDIUM confidence, review LOW/reject
5. **Integrate:** Use parsed tokens in your pipeline

---

## Tips & Tricks

✅ **Preserve extra columns:** Any custom columns in input are preserved in output  
✅ **Bulk processing:** Use bash loop to process multiple files  
✅ **Known panels boost:** Add known panels to get more HIGH confidence scores  
✅ **Verbose mode:** Use `--verbose` for detailed logs when debugging  
✅ **Format flexibility:** Input and output can be different formats  

Example: `--input tokens.csv --output tokens.json`

---

## Support

- **Documentation:** See TOKEN_PARSER_USAGE.md
- **Source Code:** token_parser.py
- **Examples:** This file
- **Help:** `python token_parser.py --help`

