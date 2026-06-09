# Electrical Panel & Circuit Extraction — Rules & Validation

## Core Rules

### Classification: Panel Labels vs. Circuit Fragments

**CRITICAL DISTINCTION:**

A token like `"2,24,33,35"` (digits + commas, no panel prefix) is a **multi_circuit fragment**, NOT a panel label. It should be classified as `multi_circuit`, NOT rejected. It was likely truncated from a full panel-circuit pair like `"EL2-2,24,33,35"`.

Similarly:
- `",14,16,18"` → multi_circuit (leading comma from text splitting)
- `"1-16,31,33"` → multi_circuit (hyphen from range notation)
- `"-4,8,10,12"` → multi_circuit (leading dash from text split)

These are **valid tokens** for the circuit continuation joiner (Step 5b) to merge back to their panel labels.

**But:**
- `"E201B"` → **invalid panel label** (pattern mismatch, classify as unknown)
- `"REFEL2"` → **invalid panel label** (reference tag, not a panel)
- `"PANEL"` → **invalid panel label** (pure word)

---

### Panel Label Format Rules

**Valid panel labels MUST:**
1. Be alphanumeric (letters + digits only, no spaces)
2. Contain at least one letter AND at least one digit (exception: single-letter panels E, U, L, P allowed)
3. Match ONE of these patterns:
   - Letter-led: `[A-Z]{1,4}[A-Z0-9]{0,5}` — e.g., E, L, EL1, LB1, NL2A3, CRL2A2
   - Digit-prefix: `[0-9][A-Z]{2,}[A-Z0-9]{0,4}` — e.g., 7LA, 4LF, 7LA2 (digit MUST be followed by 2+ letters)
4. Be ≤ 7 characters long
5. NOT start with punctuation (`,`, `?`, `'`, `!`, `[`, `(`, etc.)
6. NOT be a common English word: PANEL, SERVICE, CEILING, OWN, DOWN, OPEN, EXIT, MECH, ELEC, AREA, ROOM, ZONE

**Reject immediately (invalid panel labels):**
- `"CEILING SERVICE PANEL-1"` — has spaces
- `"E201B"` — template L-N-L doesn't match dominant pattern; outlier panel naming
- `"REFEL2"` — not a valid electrical panel (reference label, not a panel)
- `"PANEL"` — pure word, not an alphanumeric panel label
- `"OWN"` — pure word, not a panel
- `"1E"` — only 1 letter after digit (OCR artifact of E1)
- `"1L1"` — only 1 letter between digits (OCR artifact of EL1)
- `"U-6OWN-6"` — contains word "OWN"

**DO NOT reject (these are valid circuit fragments, not panels):**
- `"6,28,30"` — multi_circuit, likely truncated from panel like "E-6,28,30"
- `"2,24,33,35"` — multi_circuit, likely truncated from panel like "EL2-2,24,33,35"
- `"7,29"` — multi_circuit, likely truncated from panel
- `"1-16,31,33"` — multi_circuit with range, likely truncated
- `",14,16,18"` — multi_circuit with leading comma (OCR parsing artifact), likely truncated from "UL1-4,8,10,12,14,16,18"
- `"-4,8,10,12,14,16,18"` — multi_circuit with leading dash (text split artifact)

### Circuit Number Rules

**Valid circuit numbers:**
1. Integer in range **1–84** (inclusive)
2. Comma-separated lists acceptable: `1,3,5,7,9,11,13,15` (all parts must be 1–84)
3. No letters, spaces, or special characters except commas

**Reject immediately:**
- `85, 86, 100, 200` — out of range
- `47C`, `2B`, `1a` — contain letters
- `0` — below range
- `1,3,5,100` — mixed valid/invalid
- `+42` — mounting height, not circuit
- `112`, `114`, `156` — room numbers (pure digits, no dash)

### Pattern Discovery Rules

When discovering the dominant panel naming convention:

1. **Hard pre-filter** each label before pattern analysis:
   - Strip spaces, punctuation
   - Check length (≤ 8 chars)
   - Reject if pure-digit or pure-letter
   - Reject if contains dictionary words (OWN, PANEL, SERVICE, etc.)

2. **Template generalization**: collapse letter runs → 'L', digit runs → 'N'
   ```
   EL1         → LN
   UL1         → LN
   L8N3B2      → LNLNLN
   E           → L
   P1          → LN
   ```

3. **Dominant template selection**: choose template with ≥ 55% coverage
   - Example: if 78% of labels match "LN" (EL1, EL2, EL3, UL1, UL2, P1, U1, E), "LN" is dominant
   - Single-letter panels (E, U) score 0.85 (partial match to dominant "LN")
   - Templates with < 55% coverage are flagged as outliers

4. **Score assignment for each label**:
   - 1.0 = exact match to dominant template
   - 0.85 = single-letter if dominant starts with L
   - 0.8 = label template is extension of dominant
   - 0.5 = doesn't match dominant (possible OCR error)
   - 0.0 = failed hard pre-filter

### Confidence Scoring Rules

**Two scoring modes:**

**Mode A — Panel schedule found** (known_panels ≠ ∅):
```
score = 0.35×regex + 0.25×known_panel + 0.20×ocr_conf + 0.10×geometry + 0.10×pattern
```
- known_panel_match = 1.0 if panel in schedule, else 0.0
- pattern_score = label's score against dominant template

**Mode B — No panel schedule** (layout drawing, common case):
```
score = 0.45×regex + 0.30×ocr_conf + 0.15×geometry + 0.10×pattern
```
- Known_panel weight redistributed to OCR confidence
- Pattern recognition acts as tiebreaker

**Thresholds (both modes):**
- HIGH: score ≥ 0.85
- MEDIUM: 0.60 ≤ score < 0.85
- LOW: 0.40 ≤ score < 0.60
- REJECT: score < 0.40

**Hard rejects (override score):**
- classification ≠ "panel_circuit" → REJECT
- panel is None or empty → REJECT
- circuit outside 1–84 range → REJECT
- circuit string contains letters → REJECT
- panel fails `is_panel_token()` validation → REJECT
- **pattern_score == 0.0** (failed hard pre-filter) → REJECT
- **pattern_score == 0.5 (outlier) AND not in known_panels AND ocr_conf < 0.95** → REJECT (new in v2)
  - Catches odd labels like E201B, REFEL2 that don't match the dominant panel pattern discovered from the drawing

**Human review flags:**
- Set needs_human_review=True when:
  - confidence == LOW
  - ocr_confidence < 0.70
  - geometry-only association (no regex match)
  - pattern_score < 0.5 (outlier panel naming)

### Geometry Association Rules

For standalone PANEL_TOKEN + CIRCUIT_TOKEN pairs:

**is_below(panel, circuit):**
- circuit.y1 > panel.y2 (circuit starts below panel)
- |circuit.center_x - panel.center_x| < 1.5 × panel.width (horizontally aligned)
- Vertical distance ≤ 3 × panel.height

**is_right_of(panel, circuit):**
- circuit.x1 > panel.x2 (circuit starts to the right)
- |circuit.center_y - panel.center_y| < panel.height (vertically aligned)
- Horizontal distance ≤ 3 × panel.width

**Proximity threshold:**
- Max distance = 3 × bounding box height of panel label
- Purpose: catch nearby circuit numbers within reasonable drawing distance

**Confidence for geometry matches:**
- Base score: 0.65 MEDIUM (geometry-only is less certain than regex)
- set geometry_match=True, needs_human_review=True

### Circuit Fragment Recovery Rules

**Problem:** OCR text detector (DBNet) misses fragments like ",14,16,18" from truncated text "UL1-4,8,10,12,14,16,18"

**Solution:** Geometric association of undetected fragments

**Recovery Rules:**
1. Scan all multi_circuit tokens for pure digit+comma patterns
2. Match undetected fragments to nearest panel_circuit on same page
3. Same horizontal line: |center_y_diff| < 0.5× max_height
4. Tight spatial gap: x_right - x_left < 2.0× avg_char_width
5. Validate combined circuit list before appending
6. Absorb fragment (remove from output after appending)

**Examples:**
- `"UL1-4,8,10,12"` + fragment `,14,16,18` → `"UL1-4,8,10,12,14,16,18"` ✅
- `"EL2-2,24"` + fragment `,33,35` → `"EL2-2,24,33,35"` ✅
- Fragment too far away (gap > 2.0× char_width) → No match ❌

**File:** `pipeline/fragment_recovery.py`

---

### Circuit Continuation Rules

**Join conditions** (post-classification):

Left token (panel_circuit):
- classification == "panel_circuit"
- panel: valid, normalized
- circuit: validated digit range

Right token (circuit continuation):
- classification == "multi_circuit"
- raw_text matches `^\d{1,2}(,\d{1,2})+$` (at least one comma — pure digits + commas only)
- No conduit markers (', ", 2R, QUAD, TWIST, _DAT)

**Spatial proximity:**
- Same page
- Same horizontal line: |center_y_left - center_y_right| < 0.5 × max_height
- Tight gap: x_right - x_left < 1.5 × avg_char_width_of_left_token
- Exactly right-adjacent (not above/below)

**Validation after join:**
- Combined circuit list must pass `all_circuits_valid()`
- No duplicates after merge

**Left-to-right processing:**
- Sort multi_circuit fragments by x-coordinate
- Process in order so "UL1-4,8,10,12" → join "8,10,12" → then join "14,16,18"

### Zone Masking Rules

**Title block zone** (always masked):
- Bottom 10% of page (configurable)
- Contains company name, project number, scale, revision block

**Keyword-based zones** (masked if found):
- NOTES, GENERAL NOTES, LEGEND, SYMBOL
- REVISION, REVISIONS, SHEET NO, DRAWING NO
- DRAWN BY, CHECKED BY, APPROVED BY
- DATE, SCALE, SPECIFICATION(S)
- SEE SPECS, REFER TO, CONTRACTOR, ENGINEER, ARCHITECT

**Text-density zones** (masked if word density > 0.05 words/1000pt²):
- Multi-line paragraphs (specs, general notes, descriptions)
- Dense blocks ≥ 2000pt² area
- Expanded by 5pt margin to capture surrounding annotation

**Border strip zones** (always masked):
- Left, top, right margins: 18pt (≈ 0.25 inch)
- Thin frame around page edge (rarely contains actual drawing content)

**Zone application:**
- White-out (pixel value = 255) all masked regions in rendered image
- Happens BEFORE tiling and OCR (no token cost)
- DPI-aware coordinate conversion: PDF points → pixel coordinates

### OCR Preprocessing Rules

**For PaddleOCR (PP-OCRv4, CPU-only):**
1. Input: RGB image from PyMuPDF
2. Convert RGB → BGR (OpenCV native)
3. Preserve grayscale gradients (NO binarisation)
4. Output: 3-channel uint8 BGR image
5. Do NOT apply adaptive threshold (destroys gradient information needed by detection model)

**For EasyOCR (fallback):**
1. Input: RGB image
2. Grayscale → CLAHE contrast → adaptive threshold (binary)
3. Convert to 3-channel RGB
4. EasyOCR's CRAFT detector robust to binary images

**Text normalization:**
1. Strip leading/trailing whitespace
2. Strip leading OCR artifacts: `,`, `?`, `'`, `!`, `[`, `(`, etc.
3. Replace all dash variants (–, —, −) with ASCII hyphen
4. Uppercase all text (panel labels are uppercase)
5. O/0 disambiguation if panel schedule available

### DPI & Tile Rules

**Recommended DPI range:**
- 200 DPI: Fast, ~2-4s/tile on CPU
- 300 DPI: Better accuracy for long text lists (avoids truncation)
- 400 DPI: High quality but slow (~7-14 min for E-size sheet)

**Tile configuration:**
- tile_size = 1200px (fixed)
- overlap = 200px (fixed, 17% overlap)
- For DPI=200, E-size drawing (11"×17"):
  - Image = 2200×3400px
  - Tiles = 48 (6×8 grid with overlap)
  - Time ≈ 2–4 min on CPU

**Tile edge handling:**
- Zero-pad edges (black padding) for partial tiles at boundaries
- Deduplicator merges overlapping tokens via IOU-based NMS (threshold=0.5)

## Exception Handling

| Input | Rule Violation | Action |
|---|---|---|
| `"EL1"` alone (no circuit nearby) | Missing circuit | Classify as "unknown", attempt geometry association |
| `"29"` alone (no panel nearby) | Missing panel | Classify as "room_number" if > 84, else geometry association |
| `"EL1-85"` | Circuit out of range | confidence=REJECT, reason="Invalid circuit(s): 85" |
| `"E201B"` | Pattern mismatch | pattern_score=0.0, likely REJECT if no other confidence sources |
| `"?-?-1' 6\"-Quad-5"` | Conduit spec | Classification="unknown" or filtered by zone masking |
| OCR returns `"1L1"` | OCR artifact | Normalised to "1L1", fails is_panel_token(), rejected |
| OCR returns `",EL1-5"` | Leading punctuation | Stripped by normalizer → "EL1-5", passes validation |

