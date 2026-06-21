# Hardcoded Values Analysis & ML-Based Pattern Learning

**Date:** June 9, 2026  
**Status:** Analysis Complete - ML Design Ready

---

## Current Hardcoded Values

### 1. Panel Pattern (HARDCODED)
**Location:** `pipeline/regex_patterns.py:49-51`
```python
PANEL_TOKEN = re.compile(
    r"^([A-Z]{1,4}[A-Z0-9]{0,5}|[0-9][A-Z]{2,}[A-Z0-9]{0,4})$"
)
```
**Accepts:**
- Letter-led: L1, LB1, EL1, CRL2A2 (1-4 letters + 0-5 alphanumerics)
- Digit-led: 7LA, 4LF (digit + 2+ letters + 0-4 alphanumerics)

**Problem:** Rejects valid patterns not matching these templates

---

### 2. Circuit Range (HARDCODED)
**Location:** `pipeline/regex_patterns.py:54-56`
```python
CIRCUIT_TOKEN = re.compile(
    r"^([1-9]|[1-7][0-9]|8[0-4])$"  # Range: 1-84
)
```
**Hardcoded Value:** 1-84  
**Problem:** Hardcoded for electrical panel standard, but may not apply to all drawings

---

### 3. Equipment Tag Pattern (HARDCODED)
**Location:** `pipeline/regex_patterns.py:73-79`
```python
EQUIPMENT_TAG = re.compile(
    r"^(?:"
    r"[A-Z]{2,4}-\d{1,3}[A-Z]?"
    r"|[0-9]{1,3}[A-Z]{1}-\d{1,3}[A-Z]?"
    r"|[A-Z]{2,6}-\d{1,2}-\d{2,4}"
    r")$"
)
```
**Patterns:** FC-3, EQ-10, 2D-06, 300F-60, WSHP-4-01  
**Problem:** Hardcoded patterns may miss variations

---

### 4. Fixture Tag Pattern (HARDCODED)
**Location:** `pipeline/regex_patterns.py:82-84`
```python
FIXTURE_TAG = re.compile(
    r"^[A-Z0-9]{1,4}\s+R\d{3,}$"
)
```
**Pattern:** "B R012", "GX6 R012"  
**Problem:** Only accepts "R" prefix, may miss other fixture conventions

---

### 5. Mounting Height Pattern (HARDCODED)
**Location:** `pipeline/regex_patterns.py:87-89`
```python
MOUNTING_HEIGHT = re.compile(
    r'^\+\d+["""\'A-Z]*$'
)
```
**Pattern:** "+42", "+48AFF"  
**Problem:** Only accepts "+" prefix, may miss other height notations

---

### 6. Switch Leg Pattern (HARDCODED)
**Location:** `pipeline/regex_patterns.py:92-94`
```python
SWITCH_LEG = re.compile(
    r"^[0-9]{0,2}[a-d](?:,[0-9]{0,2}[a-d])*$"
)
```
**Pattern:** a, b, 7a, 7b, a,b  
**Hardcoded:** Lowercase a-d only  
**Problem:** May miss other switch leg conventions

---

### 7. Room Number Threshold (HARDCODED)
**Location:** `pipeline/classifier.py:129`
```python
if val > 84:  # HARDCODED: 84 is circuit max
    return PanelCircuitCandidate(token=token, classification="room_number")
```
**Hardcoded Value:** 84  
**Logic:** Anything > 84 is a room number (because circuit max is 84)  
**Problem:** Tightly coupled to circuit range

---

### 8. Panel-Circuit Separators (HARDCODED)
**Location:** `pipeline/regex_patterns.py:17-35`
```python
# Only accepts: - (hyphen), – (en-dash), — (em-dash)
r"\s*[-–—]\s*"
# Also accepts: : (colon)
# Also accepts: space (with stricter validation)
```
**Problem:** May miss other separators used in different drawings

---

## Impact of Hardcoding

### ❌ Limitations

1. **Not Data-Driven:** Same patterns applied to all drawings regardless of their conventions
2. **Inflexible:** If a drawing uses different patterns (e.g., panel-circuit with `/` or `_`), they're rejected
3. **Outlier Rejection:** Valid but uncommon patterns are marked as rejection candidates
4. **False Positives:** Equipment tags with "-" might be misclassified as panels
5. **No Adaptation:** Cannot learn facility-specific conventions

### ✅ Current Strengths

1. **Fast:** Regex patterns are O(n) and very efficient
2. **Predictable:** Same output every time
3. **Debuggable:** Easy to see why a token is classified

---

## ML-Based Solution Design

### Architecture

```
Input Tokens
    ↓
[1] Statistical Analysis
    - Panel label patterns (frequency, structure)
    - Circuit number ranges (min, max, distribution)
    - Text patterns by category
    - Separator characters used
    ↓
[2] Pattern Learning
    - Learn dominant panel naming convention
    - Learn circuit number distribution
    - Learn separator preferences
    - Learn equipment/fixture conventions
    ↓
[3] Anomaly Detection
    - Outlier panel labels (don't match dominant pattern)
    - Outlier circuit numbers (outside learned range)
    - Outlier text patterns (don't match equipment/fixture conventions)
    ↓
[4] Confidence Scoring
    - Score each token against learned patterns
    - Flag outliers/odd patterns
    - Output: classification + confidence + anomaly_score
```

### Components

#### 1. Statistical Analyzer
```python
class StatisticalAnalyzer:
    """Learn patterns from input tokens."""
    
    def analyze(self, tokens: list[str]):
        """Extract statistics about:
        - Panel label structure (letter count, digit patterns)
        - Circuit numbers (range, common values, distribution)
        - Text patterns (separators, prefixes, suffixes)
        - Category patterns (equipment, fixtures, heights)
        """
```

#### 2. Pattern Learner
```python
class PatternLearner:
    """Infer dominant patterns."""
    
    def learn_panel_pattern(self) -> PatternTemplate:
        """Most common panel naming convention"""
        # E.g., "2-letter prefix + optional digits"
        
    def learn_circuit_range(self) -> tuple[int, int]:
        """Min and max circuit numbers seen"""
        # E.g., (1, 84) or (1, 200)
        
    def learn_separator(self) -> list[str]:
        """Common separators between panel and circuit"""
        # E.g., ['-', '--', ':']
        
    def learn_rejection_patterns(self) -> dict:
        """Patterns for each rejection category"""
        # equipment, fixture, mounting_height, switch_leg, room_number
```

#### 3. Anomaly Detector
```python
class AnomalyDetector:
    """Identify outliers that don't match learned patterns."""
    
    def detect_outlier_panel(self, label: str) -> float:
        """Score: 0.0 (normal) to 1.0 (outlier)"""
        
    def detect_outlier_circuit(self, circuit: int) -> float:
        """Score: 0.0 (normal) to 1.0 (outlier)"""
        
    def detect_outlier_pattern(self, text: str, category: str) -> float:
        """Score: 0.0 (normal) to 1.0 (doesn't match category)"""
```

#### 4. Adaptive Classifier
```python
class AdaptiveClassifier:
    """Classify using learned patterns + anomaly detection."""
    
    def classify(self, token: str) -> Classification:
        """
        Returns:
        - classification: panel_circuit, equipment_tag, etc.
        - confidence: 0.0-1.0
        - anomaly_score: 0.0-1.0 (0=normal, 1=outlier)
        - reason: Why classified this way
        """
```

---

## Benefits of ML Approach

### 1. Data-Driven
```
Before: "Panel must match [A-Z]{1,4}[A-Z0-9]{0,5}"
After:  "Panel must match structure seen in 95% of drawing"
```

### 2. Adaptive
```
Building A: Panels like "EL1", "EL2", "UL1" → learns EL/UL prefix
Building B: Panels like "PA1", "PA2", "PB1" → learns PA/PB prefix
```

### 3. Outlier Detection
```
Drawing has panels: L1, L2, L3, L4, L5, L6, L7, L8, L9, XXX-1
→ XXX-1 is flagged as anomaly (doesn't match "single-letter + digit" pattern)
```

### 4. Facility-Specific
```
Facility A: Circuits 1-84 (standard) → learns range
Facility B: Circuits 1-200 (large panels) → learns range
```

### 5. No False Rejections
```
Before: Equipment "EQ-10" rejected if panel pattern changes
After: "EQ-10" learned as equipment pattern from context
```

---

## Implementation Strategy

### Phase 1: Statistical Analysis (30 min)
- Analyze input tokens
- Extract panel patterns, circuits, separators
- Generate pattern statistics

### Phase 2: Pattern Learning (45 min)
- Learn dominant panel naming
- Learn circuit distribution
- Learn category patterns (equipment, fixture, etc.)

### Phase 3: Anomaly Detection (60 min)
- Implement outlier scoring
- Calculate statistical measures (z-score, isolation forest)
- Threshold anomalies

### Phase 4: Integration (45 min)
- Replace hardcoded patterns with learned patterns
- Provide fallback to hardcoded patterns for unknown formats
- Add confidence/anomaly scores to output

### Total Time: ~3 hours implementation

---

## Example: Panel Pattern Learning

### Input Tokens
```
raw_text: L1, L2, L3, L4, L5, L6, EL1, EL2, UL1, UL2, N1, N2, XXX-1
```

### Analysis
```
Panel patterns:
  - Single letter + digit: L1, L2, L3, L4, L5, L6, N1, N2 (8 tokens, 62%)
  - Double letter + digit: EL1, EL2, UL1, UL2 (4 tokens, 31%)
  - Invalid pattern: XXX-1 (1 token, 7%)

Dominant pattern (>50%): [A-Z]{1,2}[0-9]+ 
Outliers: XXX-1 (doesn't match 93% of tokens)
```

### Classification
```
L1, L2, L3: ✅ panel_circuit (confidence: 0.98, anomaly: 0.0)
EL1, EL2: ✅ panel_circuit (confidence: 0.95, anomaly: 0.05)
XXX-1: ⚠️ panel_circuit? (confidence: 0.6, anomaly: 0.95)
       → Flag for human review
```

---

## Example: Circuit Range Learning

### Input Tokens
```
circuits: 1, 2, 3, 5, 7, 10, 12, 15, 20, 25, 30, 35, 40, 45, 50
         55, 60, 65, 70, 75, 80, 200 (outlier)
```

### Analysis
```
Circuit statistics:
  - Min: 1
  - Max: 200
  - Median: 40
  - Mode: 25
  - Distribution: Uniform 1-80, spike at 200
  
Outlier detection:
  - 200 is 2.5x the median → anomaly_score: 0.95
  - Likely not a circuit, but a room number or annotation
```

---

## Configuration

Users could control learning via parameters:

```yaml
pattern_learning:
  enabled: true
  
  # How much of data should match dominant pattern?
  dominant_pattern_threshold: 0.50  # 50%+
  
  # Anomaly score thresholds
  panel_anomaly_threshold: 0.70     # Flag if > 0.70
  circuit_anomaly_threshold: 0.70
  pattern_anomaly_threshold: 0.60
  
  # Fallback behavior
  use_hardcoded_patterns: true      # If learning insufficient
  hardcoded_pattern_threshold: 0.95 # Use hardcoded if > 95% confidence
```

---

## Next Steps

1. ✅ Analysis complete (this document)
2. ⏳ Design ML components (pattern learner, anomaly detector)
3. ⏳ Implement statistical analyzer
4. ⏳ Integrate with token_parser.py
5. ⏳ Test with diverse input files
6. ⏳ Benchmark: hardcoded vs. learned patterns

---

## Summary

### Current State
- ❌ 8+ hardcoded regex patterns
- ❌ Hardcoded thresholds (1-84, >, etc.)
- ❌ Not adaptable to facility-specific conventions
- ❌ May reject valid but uncommon patterns

### Proposed State
- ✅ Learn patterns from input data
- ✅ Adaptive thresholds based on drawing content
- ✅ Outlier detection with anomaly scores
- ✅ Data-driven classification with confidence
- ✅ Fallback to hardcoded patterns for unknown formats

### Impact
- Better accuracy for facility-specific drawings
- Fewer false rejections of valid patterns
- More transparent decision-making (learns from data)
- Anomaly detection for truly odd labels
