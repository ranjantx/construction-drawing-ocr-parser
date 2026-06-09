# OCR & Electrical Drawing Parsing — Skills & Algorithms

## Skill 1: Multi-DPI Rendering with Title Block Masking

**Purpose:** Extract drawing content at optimal resolution while skipping noise zones.

**Technique:**
```python
def iter_pages(pdf_path, dpi=300, mask_title=False):
    doc = fitz.open(pdf_path)
    for page_idx, page in enumerate(doc):
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        
        if mask_title:
            # White-out bottom 10% (title block)
            h = img.shape[0]
            img[int(h * 0.9):, :] = 255
        
        yield (page_idx, img)
```

**Key insights:**
- PyMuPDF's `get_pixmap()` is vectorized → fast at any DPI
- RGB output matches PaddleOCR/EasyOCR expectations
- Title block masking (white-out) prevents "Date", "Scale", "Drawn By" tokens polluting classifier
- DPI choice trades off speed vs. long-text truncation (300 DPI recommended for ≥30-char lists)

---

## Skill 2: Overlapping Tile Strategy with Deduplication

**Purpose:** Process large drawings that exceed GPU/CPU memory limits, while catching annotations at tile boundaries.

**Technique:**
```
tile_size = 1200px (fixed)
overlap = 200px (fixed, 17%)

For image 2200×3400:
  - X tiles: ceil((2200 - overlap) / (tile_size - overlap)) = 2
  - Y tiles: ceil((3400 - overlap) / (tile_size - overlap)) = 3
  - Total = 6 tiles (with boundary overlap)
```

**Edge handling:**
- Tiles at boundaries are padded with zeros (black border)
- OCR runs normally on padded images
- Coordinate mapper tracks tile offset: bbox_page = bbox_tile + (tile_offset_x, tile_offset_y)

**Deduplication post-OCR:**
- IOU-based NMS (Intersection-over-Union threshold = 0.5)
- For overlapping regions: keep token with highest OCR confidence
- Eliminates duplicate detections of same text in adjacent tiles

**Example:**
```
Tile 1 (x=[0-1400], y=[0-1400]) detects "EL1-5" at (100-200, 300-320)
Tile 2 (x=[1200-2400], y=[0-1400]) detects "EL1-5" at (1320-1420, 300-320)
  → IOU = 100/(100+100-IOU) ≈ 0.5 → keep highest confidence
```

---

## Skill 3: PaddleOCR vs. EasyOCR Backend Selection

**Purpose:** Choose the right OCR engine for the drawing type.

### PaddleOCR (PP-OCRv4, recommended)

**Advantages:**
- 2× faster than EasyOCR on CPU (~1–2s/tile vs. 2–4s/tile)
- Better accuracy on electrical drawings (more training data)
- Tighter confidence calibration (fewer false positives)
- Detects long text lists better (e.g., "EL1-2,4,6,8,10,12,14,20,27,29")

**Preprocessing:**
```python
def preprocess_for_paddle(img):
    # NO binarisation — PaddleOCR needs gray-value gradients
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)  # RGB → BGR
    return bgr  # 3-channel uint8, preserved gradients
```

**Model chain:**
1. **Detection (DBNet)**: Finds text bounding boxes
   - Trained on natural documents + technical drawings
   - Detects at multiple scales
   - Returns polygon coordinates
2. **Recognition (PP-OCRv4)**: Decodes text from crops
   - Input: 48px height, variable width (default 320px, boosted to 640px)
   - Handles rotated/skewed text
   - Returns confidence score per character

**When to use:**
- Production runs (electrical construction drawings)
- Long circuit lists (≥15 chars)
- Real-time performance critical

### EasyOCR (fallback)

**Advantages:**
- Works out-of-box, no tuning
- Robust to binary images
- Good fallback if PaddleOCR fails

**Preprocessing:**
```python
def preprocess_for_easyocr(img):
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    # CLAHE for contrast
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    # Adaptive threshold to binary
    binary = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                    cv2.THRESH_BINARY, blockSize=31, C=10)
    # Convert to 3-channel RGB
    rgb = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
    return rgb
```

**When to use:**
- Fallback if PaddleOCR unavailable
- Quick prototyping
- Non-electrical drawings

---

## Skill 4: Regex Classification with Decision Tree Ordering

**Purpose:** Correctly classify OCR tokens into semantic categories (panel, circuit, equipment, room, etc.) using a carefully ordered decision tree.

**Critical ordering principle:** Later steps depend on earlier rejections.

```python
def classify_token(text):
    # Step 1: Rejection patterns (catch false positives early)
    if MOUNTING_HEIGHT.fullmatch(text):           # +42", +48AFF
        return "mounting_height"
    if SWITCH_LEG.fullmatch(text):                 # a, b, 7a, 7b
        return "switch_leg"
    if FIXTURE_TAG.fullmatch(text):                # B R012, GX6 R012
        return "fixture_device_tag"
    
    # Step 2: Equipment tag BEFORE dash pattern
    # (because EQUIPMENT_TAG patterns like "FC-3" would match PANEL_CIRCUIT_DASH)
    if EQUIPMENT_TAG.fullmatch(text):              # FC-3, EQ-10, 2D-06, 300F-60
        return "equipment_tag"
    
    # Step 3: Panel-circuit compound (strongest positive signal)
    match = PANEL_CIRCUIT_DASH.search(text)
    if match:
        panel, circuit = match.groups()
        if is_panel_token(panel) and all_circuits_valid(circuit):
            return "panel_circuit"   # ✓
        else:
            return "unknown"         # Failed validation
    
    match = PANEL_CIRCUIT_COLON.search(text)
    if match:
        panel, circuit = match.groups()
        if is_panel_token(panel) and all_circuits_valid(circuit):
            return "panel_circuit"
        else:
            return "unknown"
    
    # Step 4: Standalone tokens (geometry pass needed)
    if ROOM_NUMBER_PURE.fullmatch(text):           # 112, 114, 156 (>84)
        return "room_number"
    if CIRCUIT_TOKEN.fullmatch(text):              # 1, 5, 29, 84
        return "unknown"                           # Geometry pass will associate panel
    if PANEL_TOKEN.fullmatch(text):                # L1, EL1, 7LA
        return "unknown"                           # Geometry pass will associate circuit
    
    # Step 5: Default
    return "unknown"
```

**Why order matters:**

| If we checked | Problems |
|---|---|
| EQUIPMENT_TAG after PANEL_CIRCUIT_DASH | "FC-3" matches dash pattern → false panel_circuit(F, C-3) |
| SWITCH_LEG after PANEL_CIRCUIT_DASH | "7a" matches dash pattern → false panel_circuit(7, a) |
| PANEL_CIRCUIT before hard rejects | "+42"" treated as panel-circuit |

---

## Skill 5: Panel Pattern Recognition (Structural Matching)

**Purpose:** Discover the dominant naming convention used in a drawing, then use it to filter OCR noise and boost confidence.

**Algorithm:**

```python
class PanelPatternRecognizer:
    def fit(self, panel_labels):
        # Step 1: Hard pre-filter
        candidates = [lbl for lbl in panel_labels if self._passes_filter(lbl)]
        
        # Step 2: Template generalization
        # EL1 → LN, L8N3B2 → LNLNLN, E → L
        templates = [self._to_template(c) for c in candidates]
        
        # Step 3: Frequency analysis
        template_counts = Counter(templates)
        
        # Step 4: Select dominant (≥55% coverage)
        for tmpl, count in template_counts.most_common():
            if count / len(candidates) >= 0.55:
                self.dominant_template = tmpl
                break
    
    def score_label(self, label):
        if not self._passes_filter(label):
            return 0.0      # Failed hard filter
        
        tmpl = self._to_template(label)
        if tmpl == self.dominant_template:
            return 1.0      # Exact match
        if tmpl == "L" and self.dominant_template.startswith("L"):
            return 0.85     # Single-letter panel (E, U) vs. dominant "LN"
        if tmpl.startswith(self.dominant_template):
            return 0.80     # Extended version (e.g. "LNL" when dominant is "LN")
        
        return 0.5          # Doesn't match (possible OCR error)
```

**Benefits:**
- Rejects OCR artifacts like "1L1" (OCR misread of EL1) automatically
- Boosts confidence for conventional panels matching drawing's pattern
- Catches outliers like "E201B" (low pattern score → possibly invalid)

**Example:**
```
Input: [EL1, EL2, EL3, UL1, UL2, E, U, L8N3B2, E201B]
Templates: [LN, LN, LN, LN, LN, L, L, LNLNLN, LNLN]
Counts: {LN:5, L:2, LNLNLN:1, LNLN:1}
Coverage: 5/9 = 55.6% → Dominant = "LN"

Scores:
  EL1     → LN    → 1.0 (exact)
  E       → L     → 0.85 (single-letter subset)
  L8N3B2  → LNLNLN → 0.5 (doesn't match LN)
  E201B   → LNLN  → 0.5 (doesn't match LN)
```

---

## Skill 6: Zone Masking (PDF Native Text Layer)

**Purpose:** Identify and exclude non-drawing regions (title block, notes, legends) BEFORE OCR to save processing time and reduce noise.

**Technique:**
```python
def detect_zones(pdf_path, page_index=0):
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    pw, ph = page.rect.width, page.rect.height
    zones = []
    
    # Zone 1: Fixed title block (bottom 10%)
    zones.append(MaskedZone(0, ph*0.9, pw, ph, "title_block"))
    
    # Zone 2: Border strips (left, top, right)
    zones.append(MaskedZone(0, 0, 18, ph, "border_left"))
    
    # Zone 3: Keyword-based (NOTES, LEGEND, REVISION, etc.)
    for block in page.get_text("dict").get("blocks", []):
        text = block_text(block).upper()
        if any(kw in text for kw in ["NOTES:", "LEGEND", "REVISION"]):
            zones.append(expand_zone(block, by=20%))
    
    # Zone 4: Text-density based (dense paragraph = notes)
    for block in ...:
        if word_density(block) > 0.05:
            zones.append(zone_from_block(block))
    
    return zones
```

**Key advantages:**
- Uses **native PDF text layer** (no OCR cost, < 1s per page)
- No false negatives — if keyword missing, zone just doesn't mask (harmless)
- DPI-aware conversion: PDF points → pixel coordinates at render time
- White-out is destructive but safe (no real drawing content in margins)

---

## Skill 7: Circuit Continuation Joining (Post-Classification)

**Purpose:** Merge split circuit lists that OCR detector fragmented into multiple boxes, while rejecting invalid panel labels and false circuits.

**Root cause:** PaddleOCR's DBNet detection splits long text like "UL1-4,8,10,12,14,16,18" into:
- Box 1: "UL1-4,8,10,12" → classified as panel_circuit(UL1, 4,8,10,12)
- Box 2: "14,16,18" → classified as multi_circuit(14,16,18)
- Box 3 (rare): ",14,16,18" → starts with comma from text split boundary

**Critical:** Box 2 and 3 are VALID circuit fragments that should be rejoined, NOT rejected.

**Solution:** Post-classification join with strict spatial & semantic criteria.

```python
def join_circuit_continuations(candidates):
    pc_list = [(i, c) for i, c in enumerate(candidates)
               if c.classification == "panel_circuit"]
    mc_list = [(i, c) for i, c in enumerate(candidates)
               if c.classification == "multi_circuit"]
    
    mc_list.sort(key=lambda x: x[1].token.bbox.x1)  # Left-to-right
    
    for mc_idx, mc in mc_list:
        raw = mc.token.raw_text.strip()
        
        # Guard 1: Fragment must be a pure circuit list (digits + commas/dashes)
        # Accept: "14,16,18" (no leading punctuation)
        # Accept: "2,24,33,35" (any number of circuits)
        # Accept: "-14,16" (leading dash from text split)
        # Accept: ",14,16" (leading comma from text split)
        # Reject: "E-14" (mixed with letters)
        # Reject: "EL2" (just a panel label)
        if not _is_pure_circuit_fragment(raw):
            continue
        
        # Find nearest LEFT panel_circuit (left-to-right processing)
        for pc_idx, pc in pc_list:
            # Guard 2: Same line
            if abs(pc.center_y - mc.center_y) > 0.5 * max_height:
                continue
            
            # Guard 3: Tight gap (< 1.5× avg char width)
            gap = mc.x1 - pc.x2
            if gap > 1.5 * avg_char_width(pc.token):
                continue
            
            # Guard 4: Clean leading punctuation before combining
            cleaned = raw.lstrip(',-')  # Remove leading dash/comma
            
            # Guard 5: Combined list valid
            combined = f"{pc.circuit},{cleaned}"
            if not all_circuits_valid(combined):
                continue
            
            # JOIN
            pc.circuit = combined
            absorbed.add(mc_idx)
            break  # Don't pair this fragment with multiple panels
    
    return [c for i, c in enumerate(candidates) if i not in absorbed]

def _is_pure_circuit_fragment(text):
    """
    True if text is a valid circuit fragment (digits, commas, leading dashes/commas OK).
    Examples:
      "14,16,18"      → True (pure circuits)
      "2,24,33,35"    → True
      "-14,16"        → True (leading dash from text split)
      ",14,16"        → True (leading comma from text split)
      "1-16,31,33"    → True (range notation)
      "E-14"          → False (mixed with letter)
      "EL2"           → False (panel label, not circuit)
      "PANEL"         → False (word)
    """
    # Strip leading dashes/commas which come from text splitting
    cleaned = text.lstrip(',-')
    if not cleaned:
        return False
    
    # Must be all digits/commas (at least one comma means it's a list)
    if not all(c.isdigit() or c == ',' for c in cleaned):
        return False
    
    # At least one comma (single number without comma is handled elsewhere)
    if ',' not in cleaned:
        return False
    
    return True
```

**Why safe:**
- Only merges POST-classification tokens with known roles
- Right fragment must be pure circuits (digits + commas/dashes, with leading punctuation stripped)
- Spatial proximity enforced (< 1.5× char width)
- Combined list validated before merge
- Left-to-right processing allows chain joins:
  - Start: "UL1-4,8,10,12" + "14,16,18" + "20,22,24"
  - After 1st join: "UL1-4,8,10,12,14,16,18" + "20,22,24"
  - After 2nd join: "UL1-4,8,10,12,14,16,18,20,22,24" ✓

**Examples of correct joins:**
```
Input:    UL1-4,8,10,12  |  14,16,18  |  20,22
Result:   UL1-4,8,10,12,14,16,18,20,22  ✓

Input:    E-6  |  ,28,30  (comma from text split)
Result:   E-6,28,30  ✓

Input:    EL2-2,24  |  -33,35  (leading dash)
Result:   EL2-2,24,33,35  ✓
```

**Examples of CORRECTLY REJECTED joins:**
```
Input:    E-6  |  EL2  (EL2 is a panel, not circuit)
Action:   Skip (EL2 fails _is_pure_circuit_fragment)

Input:    UL1-4,8,10,12  |  E201B  (E201B invalid panel)
Action:   Skip (E201B not classified as multi_circuit; it's unknown)

Input:    L1-5  |  (gap > 1.5× char width)
Action:   Skip (spatial proximity guard fails)
```

---

## Skill 8: Confidence Scoring with Multi-Source Weighting

**Purpose:** Combine regex signal, panel schedule, OCR quality, geometry, and pattern recognition into a single confidence score.

**Formula (Mode B — no panel schedule):**
```
score = 0.45×regex + 0.30×ocr_conf + 0.15×geometry + 0.10×pattern

Components:
  regex        = 1.0 (already confirmed by classifier)
  ocr_conf     = raw OCR confidence (0.0–1.0) from PaddleOCR/EasyOCR
  geometry     = 0.8 if geometry_match else 0.0 (spatial proximity indicates reliability)
  pattern      = label's score against drawing's dominant naming convention

Example: EL1-5, ocr_conf=0.90, pattern=1.0, no geometry
  score = 0.45 + 0.27 + 0.0 + 0.10 = 0.82 → MEDIUM confidence
```

**Benefits:**
- No single source dominates (balanced weighting)
- Pattern recognition disambiguates outliers (E201B gets low pattern score)
- Geometry is conservative (0.8 vs 1.0) — spatial proximity less reliable than regex
- OCR confidence normalized (directly reflects model uncertainty)

---

## Skill 9: Long Circuit List Handling (Avoids Truncation)

**Problem:** Recognition model has max-width constraint.
- PaddleOCR default: 320px width at 32px height
- "UL1-4,8,10,12,14,16,18" at DPI=200 → ~480px wide → truncated to "UL1-4,8,10,12"

**Solutions (in priority order):**

1. **Increase recognition input width:**
   ```python
   text_rec_input_shape=[3, 48, 640]  # doubled from [3, 48, 320]
   ```
   - Upside: single model can handle longer strings
   - Downside: slower (more parameters)

2. **Use higher DPI rendering:**
   ```
   DPI=300 instead of DPI=200
   → Same string is 480px at larger font size
   → Recognized in full without truncation
   ```
   - Upside: better accuracy overall
   - Downside: slower rendering, more tiles

3. **Circuit continuation joiner:**
   - If above fail, join fragments post-OCR
   - "UL1-4,8,10,12" + "14,16,18" → "UL1-4,8,10,12,14,16,18"

**Recommended:** Use DPI=300 + circuit joiner as safety net.

---

## Skill 10: CPU-Only Optimization

**Constraints:** No GPU available. Must run on standard Windows/Linux machines.

**Optimizations:**

1. **Image preprocessing in CV2 (vector operations):**
   - CLAHE, adaptive threshold, deskew all vectorized
   - < 100ms per tile

2. **Tiling strategy:**
   - 1200×1200px tiles fit in CPU L3 cache
   - Overlap reduces edge artifacts
   - Total time proportional to tile count, not image size

3. **Deduplication with IOU (early termination):**
   - Sort by confidence desc
   - Greedy NMS (one pass, linear time)
   - No nested loops over full token set

4. **PaddleOCR multi-variant init:**
   - Try PP-OCRv4 first (faster, avoids PIR bug)
   - Fall back to PP-OCRv3 or PP-OCRv5
   - Smoke-test to confirm working version

5. **Native PDF text layer for zones:**
   - Zero-cost pre-processing
   - 1 second per page instead of minutes of OCR

**Performance (typical E-size drawing, DPI=200):**
- Rendering: 10s
- Tiling: < 1s
- OCR (48 tiles, PaddleOCR): 60–90s
- Post-processing: < 10s
- **Total: ~2 minutes**

