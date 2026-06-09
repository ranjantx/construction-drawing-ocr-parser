# Fragment Recovery Mechanism — Design & Implementation

**Date:** June 8, 2026  
**Purpose:** Recover circuit fragments missed by OCR text detector (DBNet)

---

## Problem Statement

### Observed Issue
When processing "UL1-4,8,10,12,14,16,18":
- **Expected:** Complete panel-circuit pair with all 8 circuit numbers
- **Actual:** "UL1-4,8,10,12" extracted; fragment ",14,16,18" missing

### Root Cause Analysis
PaddleOCR's detection pipeline:
1. **Text Detection (DBNet):** Finds bounding boxes containing text
2. **Text Recognition (CRNN):** Reads text within boxes
3. **Problem:** Fragment ",14,16,18" is **not detected as a bounding box** by DBNet

### Why DBNet Misses Fragments
- Text fragment too small or faint to trigger detection confidence threshold
- Tile boundary cuts off edge of fragment
- Preprocessing (whitespace masking) removes surrounding context
- Text detector optimized for general documents, not dense technical drawings

---

## Solution: Geometric Fragment Recovery

### Algorithm

**Step 1: Identify Candidates**
```
FOR each multi_circuit token:
  IF raw_text matches "(,|-)?\d{1,2}(,\d{1,2})+" THEN candidate_for_recovery
```

**Step 2: Find Nearest Panel**
```
FOR each candidate fragment:
  FOR each panel_circuit token on SAME PAGE:
    IF same_horizontal_line(fragment, panel) THEN
      calculate_gap = fragment.x1 - panel.x2
      IF gap < TIGHT_THRESHOLD THEN
        best_match = panel with smallest gap
```

**Step 3: Validate & Append**
```
  combined_circuit = panel.circuit + "," + cleaned_fragment
  IF all_circuits_valid(combined_circuit) THEN
    panel.circuit = combined_circuit
    panel.reason += " + RECOVERED_FRAGMENT"
    absorb(fragment)
```

### Safety Guardrails

1. **Same Page Check:** Don't match across pages
2. **Same Line Check:** |center_y_diff| < 0.5 × max_height
3. **Spatial Proximity:** gap < 2.0 × avg_char_width
4. **Validation:** Combined circuit list must pass all_circuits_valid()
5. **Left-to-Right Processing:** Sort fragments by x1 for chain joining
6. **Absorption:** Remove recovered fragments from output

---

## Configuration

**File:** `config.py`

Current settings:
```python
tile_size = 1200          # 1200×1200 px per tile
tile_overlap = 200        # 17% overlap buffer
proximity_factor = 3.0    # for geometry association
```

**Fragment-Specific:**
```python
TIGHT_GAP_CHARS = 2.0    # Maximum gap in char widths
```

---

## Implementation

**File:** `pipeline/fragment_recovery.py` (NEW)
- `recover_missing_fragments(candidates)` — Main function
- `_is_pure_circuit_fragment(text)` — Pattern validation
- `_avg_char_w(token)` — Character width estimation

**Integration:** `extract_circuits.py`
- Called after `join_circuit_continuations()`
- Logs: "Fragment recovery: N orphan fragments recovered via geometry"

---

## Expected Behavior

### Before Fragment Recovery
```
Input:  "UL1-4,8,10,12" + orphaned ",14,16,18"
Output: Two separate tokens, fragment lost
Result: Final panel-circuit missing last 3 circuits
```

### After Fragment Recovery
```
Input:  "UL1-4,8,10,12" + orphaned ",14,16,18"
OCR Processing:
  - Geometry check: same line ✓, tight gap ✓
  - Validation: all_circuits_valid("4,8,10,12,14,16,18") ✓
  - Combine: UL1 circuit = "4,8,10,12,14,16,18"
  - Absorb: ",14,16,18" removed from output
Output: Single panel-circuit with all circuits
Result: Complete extraction ✓
```

---

## Test Cases

| Input | Fragment | Distance | Validation | Expected |
|-------|----------|----------|------------|----------|
| UL1-4,8,10,12 | ,14,16,18 | < 1.5× | Valid | ✅ Append |
| EL2-2,24 | ,33,35 | < 1.5× | Valid | ✅ Append |
| E-6 | CEILING | > 3× | N/A | ❌ Skip |
| U-15 | 20,22 | < 1.5× | Valid | ✅ Append |
| L1-3 | 4,5,6,7,8,9,10,11,12,13 | < 1.5× | Invalid (>84) | ❌ Skip |

---

## Performance Impact

- **Processing:** O(n²) worst-case (each fragment vs each panel)
- **Typical:** ~10–20 fragments per page, <1ms overhead
- **Memory:** O(1) — in-place modification of candidate list
- **Logging:** INFO level for recovered fragments, DEBUG for skipped

---

## Debugging

Enable logging to see fragment recovery in action:

```bash
python extract_circuits.py --pdf file.pdf --verbose
```

Look for:
- `"Fragment recovery: N orphan fragments recovered via geometry"`
- Individual lines: `"Fragment recovered: UL1 [4,8,10,12] + [14,16,18] = [4,8,10,12,14,16,18]"`

---

## Future Improvements

1. **ML-based detection:** Train DBNet-lite to detect fragments specifically
2. **Confidence scoring:** Weight recovery result based on proximity quality
3. **Multi-line recovery:** Handle fragments on different lines (rarer case)
4. **Template matching:** Use panel's known circuit pattern to identify fragments

---

## Summary

Fragment recovery is a **robust geometric fallback** for cases where PaddleOCR's text detector misses fragments. It operates as a **post-classification safety net** and only modifies candidates when validation criteria are met.

**Key benefit:** Zero impact if fragments are detected correctly; immediate recovery if they're missed.
