# `.claude` Folder — Knowledge Base for Electrical Panel & Circuit Extraction

## Overview

This folder contains comprehensive documentation for the electrical panel and circuit number extraction system from construction PDF drawings. Refer here for understanding the algorithms, rules, and techniques used in the `parser/` project.

---

## Files in This Folder

### 1. **CLAUDE.md** — Project Overview & Architecture
- Overall project goal and constraints
- System architecture diagram
- Core algorithm summaries (pattern recognition, zone masking, circuit joining, confidence scoring)
- Critical implementation details (decision tree ordering, panel token rules, etc.)
- File organization and recent changes
- Performance targets and next steps

**Read this first for:**
- High-level understanding of the system
- How the pieces fit together
- Recent bug fixes and design decisions

### 2. **RULES.md** — Validation Rules & Thresholds
- Panel label format rules (what's valid, what's rejected)
- Circuit number validation rules (range 1–84, no letters, etc.)
- Pattern discovery rules (hard pre-filter, template generalization, dominant template selection)
- Confidence scoring rules (both modes: with/without panel schedule)
- Geometry association rules (is_below, is_right_of, proximity)
- Circuit continuation joining rules
- Zone masking rules
- OCR preprocessing rules
- Exception handling table

**Read this when:**
- Debugging why a token was rejected
- Implementing new validation logic
- Adding exceptions or special cases
- Tuning confidence thresholds

### 3. **SKILLS.md** — Algorithms & Techniques
10 detailed skills with code examples:

1. **Multi-DPI Rendering with Title Block Masking** — How to render PDFs at optimal resolution while skipping noise
2. **Overlapping Tile Strategy** — Large drawing processing with deduplication
3. **PaddleOCR vs. EasyOCR Selection** — When to use each backend
4. **Regex Classification Decision Tree** — Why order matters in token classification
5. **Panel Pattern Recognition** — Learning dominant naming convention
6. **Zone Masking (PDF Native Text Layer)** — Excluding notes/legends without OCR cost
7. **Circuit Continuation Joining** — Merging split circuit lists post-OCR
8. **Confidence Scoring with Multi-Source Weighting** — Combining regex, OCR quality, geometry, and pattern
9. **Long Circuit List Handling** — Avoiding recognition model truncation
10. **CPU-Only Optimization** — Performance techniques for CPU-bound processing

**Read this when:**
- Implementing a feature and need step-by-step algorithm
- Optimizing for speed or accuracy
- Trying to understand WHY a decision was made (not just WHAT)
- Extending the system with new capabilities

---

## Cross-Reference Guide

| Topic | Primary | Secondary |
|---|---|---|
| Panel label validation | RULES.md § Panel Label Format | pipeline/regex_patterns.py |
| Circuit validation | RULES.md § Circuit Number Rules | pipeline/regex_patterns.py::all_circuits_valid |
| Confidence scoring | RULES.md § Confidence Scoring | pipeline/confidence_scorer.py |
| Pattern recognition | SKILLS.md § Skill 5 | pipeline/panel_pattern_recognizer.py |
| Zone masking | SKILLS.md § Skill 6 | pipeline/zone_masker.py |
| Decision tree order | SKILLS.md § Skill 4 | pipeline/classifier.py |
| Circuit joining | SKILLS.md § Skill 7 | pipeline/text_merger.py::join_circuit_continuations |
| Long lists | SKILLS.md § Skill 9 | pipeline/text_merger.py (+ set DPI=300) |
| CPU optimization | SKILLS.md § Skill 10 | pipeline/ocr_engine.py::_try_init_paddle |

---

## Common Questions & Answers

### Q: Why was my panel label rejected?
**A:** Check RULES.md § Panel Label Format. Common reasons:
- Contains spaces: `"CEILING SERVICE PANEL-1"` ✗
- Only 1 letter after digit: `"1E"` ✗ (should be `"1EA"` with 2+ letters)
- Is a dictionary word: `"OWN"` ✗
- Starts with punctuation: `",EL1"` ✗ (normalizer strips it → `"EL1"` ✓)

### Q: How do I tune confidence thresholds?
**A:** Edit `config.py` constants:
```python
conf_high   = 0.85  # Change to 0.80 for more MEDIUM→HIGH
conf_medium = 0.60
conf_low    = 0.40
```
Then re-run tests in `tests/test_accuracy.py` to verify precision/recall targets still met.

### Q: Why are my notes/legends being OCR'd?
**A:** Zone masking only works on PDFs with native text layers. If your PDF is scanned (image-only), zones can't be detected. Workaround: manually mask those regions before running extraction.

### Q: Can I use EasyOCR instead of PaddleOCR?
**A:** Yes. Set `--ocr-backend easyocr`. See SKILLS.md § Skill 3 for pros/cons. EasyOCR is slower but more robust for unusual drawings.

### Q: My panel labels are weird like `"3LA2X4"`; how do I handle them?
**A:** Update panel pattern recognizer threshold. Edit `pipeline/panel_pattern_recognizer.py`:
```python
DOMINANT_THRESHOLD = 0.40  # Lower threshold to accept more diversity
```
But note: lower threshold means more false positives. Prefer adding those panels to known_panels instead.

---

## Session History

### Session 1 (Initial Build)
- Designed regex patterns and decision tree
- Implemented core pipeline (PDF → tiles → OCR → classify → score)
- Built 185 unit tests (all passing)

### Session 2 (PaddleOCR Debug + Long Lists)
- Fixed PaddleOCR zero-output: removed binarisation, preserved gradients
- Fixed long circuit list truncation: added circuit continuation joiner
- Fixed confidence scoring: redistributed weights when no panel schedule

### Session 3 (Pattern Recognition & Zone Masking)
- Added `PanelPatternRecognizer` to auto-discover drawing's naming convention
- Added `ZoneMasker` to exclude title blocks/notes/legends before OCR
- Added `join_circuit_continuations()` with left-to-right sorting for chain joins
- Created comprehensive RULES.md, SKILLS.md, CLAUDE.md documentation

---

## Performance Benchmarks

**Test Configuration:** Windows laptop, Intel CPU, Python 3.13, PaddleOCR PP-OCRv4

| Task | Time | Notes |
|---|---|---|
| Render E-size @ 300 DPI | ~10s | PyMuPDF vectorized, fast |
| Detect zones | ~1s | Native PDF text layer scan |
| Generate 48 tiles | < 1s | Simple array slicing |
| OCR 48 tiles | 60–90s | PaddleOCR, 1–2s/tile average |
| Deduplication | < 1s | Greedy NMS, linear time |
| Classification & scoring | < 5s | Vectorized regex, no I/O |
| Excel output | < 2s | openpyxl, 250 rows |
| **TOTAL** | **~2–3 min** | **Real-world E-size drawing** |

---

## Debugging Checklist

If extraction is failing or producing unexpected results:

1. **Check logs** (`--verbose` flag)
   - Look for zone masking: "Zone detection page 0: N zones masked"
   - Look for pattern discovery: "Dominant panel template: 'LN' coverage=78%"

2. **Verify input PDF**
   - Is it actually a drawing (not scanned image)?
   - Does it have native text layer? (check with pdftotext utility)
   - Are panel labels in the drawing itself, not in title block?

3. **Check OCR quality**
   - Run `validate_paddle.py` or `validate_joiner.py` to test OCR on a single tile
   - If many "unknown" classifications, OCR quality may be poor

4. **Test unit cases**
   - Run `pytest tests/test_regex.py -v` to check pattern matching
   - Run `pytest tests/test_classifier.py -v` to check decision tree

5. **Inspect output**
   - Open output Excel, check "Rejected" sheet
   - Look at rejection reasons in `reason` column
   - Check "Review" sheet for items flagged as `needs_human_review=True`

---

## Further Reading

- **PaddleOCR Docs:** https://paddleocr.readthedocs.io/
- **EasyOCR Docs:** https://github.com/JaidedAI/EasyOCR
- **PyMuPDF Docs:** https://pymupdf.readthedocs.io/
- **Pydantic v2 Docs:** https://docs.pydantic.dev/latest/
- **OpenCV Docs:** https://docs.opencv.org/

