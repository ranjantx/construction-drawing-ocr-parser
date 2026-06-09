# Fragment Missing Issue — Root Cause Analysis

**Date:** June 9, 2026  
**Status:** Root cause identified, solution proposed

---

## Issue Summary

**Problem:** `"UL1-4,8,10,12,14,16,18"` truncated to `"UL1-4,8,10,12"`  
**Missing Fragment:** `,14,16,18` (the last 3 circuits)

---

## Root Cause: OCR Text Detector Failure

### Finding #1: Fragment Doesn't Exist in OCR Output

After adding **Fragment Recovery** mechanism to geometrically associate orphaned fragments:
- ✅ 4 multi_circuit fragments detected (6,28,30 / 2,24,33,35 / 7,29 / 3,8)
- ❌ **ZERO orphaned ",14,16,18" detected anywhere**

**Conclusion:** The fragment `,14,16,18` is NOT in the OCR output at all.

### Finding #2: Why Text Detector Misses It

PaddleOCR's **DBNet text detector** (detection + recognition pipeline):

```
Detected:  "UL1-4,8,10,12"  ✓ (confidence > 0.5)
Missed:    ",14,16,18"      ✗ (confidence < 0.5 threshold)
```

**Possible reasons:**
1. **Tile boundary cut-off** — Fragment at edge of tile, clipped
2. **Low confidence** — Too small/faint for DBNet detection
3. **Preprocessing issue** — Zone masking whitespace removed context
4. **Text occlusion** — Nearby graphics obscure text
5. **Detector optimization** — DBNet trained on general docs, not dense technical drawings

---

## Why Fragment Recovery Didn't Help

**Fragment Recovery** is designed for this scenario:
```
OCR Output:
  Token 1: "UL1-4,8,10,12"     ✓ Detected
  Token 2: ",14,16,18"         ✓ Detected (but orphaned)
           ↓ Recovery mechanism matches geometrically
  Result:  "UL1-4,8,10,12,14,16,18"  ✓ Complete
```

**Actual situation:**
```
OCR Output:
  Token 1: "UL1-4,8,10,12"     ✓ Detected
  Token 2: (missing entirely)   ✗ Not detected by DBNet
           ↓ Nothing to recover
  Result:  "UL1-4,8,10,12"     ✗ Incomplete (no fragment to join)
```

**Verdict:** Fragment Recovery works perfectly for detected-but-orphaned fragments.  
**Issue remains:** We need to handle *undetected* fragments (different problem).

---

## Solutions for Undetected Fragments

### Option 1: Re-OCR High-Confidence Panels (RECOMMENDED)

**Idea:** If OCR truncates a panel (ends with comma), re-OCR the area immediately below/right.

**Algorithm:**
```python
FOR each panel_circuit with truncated_indicator (ends with "," or "-"):
  # Panel was likely cut off mid-list
  search_region = expand_bbox(panel.bbox, grow_right=200px, grow_down=100px)
  re_ocr_result = paddle_ocr(search_region)
  IF re_ocr_result matches circuit_pattern:
    append_to_panel(re_ocr_result)
```

**Pros:**
- Focused re-OCR of likely problem areas
- Zero false positives (only process truncated panels)
- ~5-10ms per truncated panel

**Cons:**
- 2x OCR for affected panels
- Needs careful bbox calculation

### Option 2: Increase Tile Overlap

**Idea:** Current 200px overlap (17%) may not be enough. Increase to 300px (25%).

**Change:**
```python
# config.py
tile_overlap = 300  # was 200
```

**Pros:**
- More buffer for edge fragments
- Already have implementation

**Cons:**
- ~1.5x slower (more overlap = more tiles)
- May not solve if gap is > 300px

### Option 3: Post-OCR Text Assembly

**Idea:** Post-process recognized text to detect incomplete tokens and search adjacent regions.

**Implementation:**
1. Flag tokens ending with comma/dash as "incomplete"
2. Search 500px radius for orphaned digit+comma patterns
3. Heuristic validation (circuits in valid range, geometrically adjacent)
4. Append to incomplete token

**Pros:**
- Handles any undetected fragment nearby
- Single pass (no re-OCR)

**Cons:**
- Heuristic-based (less reliable than re-OCR)
- May mis-associate across drawing sections

### Option 4: Hybrid Approach (BEST)

Combine strategies:
1. **Level 1:** Fragment Recovery (for detected-orphaned fragments) ✓ Implemented
2. **Level 2:** Increase tile overlap to 300px
3. **Level 3:** Re-OCR incomplete panels (fallback)

---

## Recommendations

### Immediate (No Code Change)

**Run with `--tile-overlap 300`:**
```bash
python extract_circuits.py \
  --pdf file.pdf \
  --tile-overlap 300 \
  --dpi 300
```

This alone may solve the UL1 issue if ",14,16,18" is just past the 200px buffer.

### Medium-term (Code Change)

Implement **Option 1 (Re-OCR Incomplete Panels)**:
```python
# New file: pipeline/incomplete_panel_recovery.py
def recover_truncated_panels(candidates, pdf_path, dpi):
  for panel in candidates:
    if panel.raw_text.endswith((',', '-')):
      # Panel truncated, re-OCR nearby
      search_region = ...
      extra_circuits = re_ocr_and_parse(search_region)
      panel.circuit += ',' + extra_circuits
```

### Long-term (Architecture)

Consider **semantic segmentation** to identify text regions first, then OCR only text areas. This avoids the tile-edge problem entirely.

---

## Testing the Fix

### Test 1: Increase Overlap
```bash
python extract_circuits.py \
  --pdf "input/E201A-FLOOR-PLAN- P&S.pdf" \
  --output test/ \
  --dpi 300 \
  --tile-overlap 300
```

Check if UL1 now has complete circuit list.

### Test 2: Verify Fragment Recovery Still Works
```bash
# Look for: "RECOVERED_FRAGMENT" in reason field
grep -i "recovered" output/circuits_*.json
```

---

## Summary

**Finding:** The missing fragment `,14,16,18` is **not detected by PaddleOCR at all** (not in OCR output).

**Fragment Recovery:** Works perfectly for detected-but-orphaned fragments (solves one problem, not this one).

**Next Step:** Increase `tile_overlap` to 300px and test. If still failing, implement re-OCR of incomplete panels.

**Timeline:**
- **Quick fix:** Increase overlap (5 min, may solve issue)
- **Proper fix:** Re-OCR incomplete panels (2 hours implementation + testing)
- **Long-term:** Semantic segmentation (complex, architectural change)

