"""
Pattern Learner — Learn dominant patterns from input tokens instead of hardcoded regexes.

This module analyzes actual token data to learn:
1. Dominant panel naming conventions
2. Circuit number ranges and distributions
3. Common separators (-, :, space, etc.)
4. Text patterns for rejection categories (equipment, fixture, mounting height, etc.)
5. Anomaly detection for outliers

Replaces hardcoded patterns with data-driven learning.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CircuitStatistics:
    """Statistics about circuit numbers found in tokens."""
    min_circuit: int
    max_circuit: int
    mean_circuit: float
    median_circuit: int
    circuits_seen: set[int]
    count: int

    @property
    def range(self) -> tuple[int, int]:
        return (self.min_circuit, self.max_circuit)

    @property
    def spread(self) -> int:
        return self.max_circuit - self.min_circuit


@dataclass
class PanelPatternTemplate:
    """Learned panel naming pattern."""
    pattern_description: str  # e.g., "1-2 letters + digits"
    regex_pattern: str  # e.g., r"^[A-Z]{1,2}\d+$"
    frequency: int  # How many tokens match this pattern
    percentage: float  # Percentage of all panels
    examples: list[str]  # Top 5 examples


@dataclass
class LearnerConfig:
    """Configuration for pattern learning."""
    min_samples: int = 10  # Minimum samples to learn from
    dominant_pattern_threshold: float = 0.50  # Pattern must be >50% to be dominant
    panel_anomaly_threshold: float = 0.70  # Anomaly score threshold
    circuit_anomaly_threshold: float = 0.70
    use_hardcoded_fallback: bool = True  # Use hardcoded patterns if learning fails


# ─────────────────────────────────────────────────────────────────────────────
# Statistical Analyzer
# ─────────────────────────────────────────────────────────────────────────────

class StatisticalAnalyzer:
    """Analyze raw tokens to extract patterns."""

    def __init__(self):
        self.panel_patterns: dict[str, int] = Counter()
        self.circuits: list[int] = []
        self.separators: dict[str, int] = Counter()
        self.equipment_patterns: dict[str, int] = Counter()
        self.fixture_patterns: dict[str, int] = Counter()
        self.height_patterns: dict[str, int] = Counter()

    def analyze_tokens(self, raw_texts: list[str]) -> None:
        """Analyze a batch of raw text tokens."""
        for text in raw_texts:
            text = text.strip()
            if not text:
                continue

            # Extract separators (-, :, space)
            if '-' in text:
                self.separators['-'] += 1
            if ':' in text:
                self.separators[':'] += 1
            if ' ' in text:
                self.separators[' '] += 1

            # Extract panel patterns
            self._extract_panel_pattern(text)

            # Extract circuits
            self._extract_circuits(text)

            # Extract rejection category patterns
            self._extract_rejection_patterns(text)

    def _extract_panel_pattern(self, text: str) -> None:
        """Identify panel naming patterns."""
        # Split by common separators
        for sep in ['-', ':', ' ']:
            if sep in text:
                parts = text.split(sep)
                if len(parts) >= 2:
                    panel_candidate = parts[0].strip()

                    # Learn pattern structure
                    pattern = self._get_pattern_structure(panel_candidate)
                    if pattern:
                        self.panel_patterns[pattern] += 1
                        break

    def _extract_circuits(self, text: str) -> None:
        """Extract circuit numbers."""
        # Find all numbers 1-999
        numbers = re.findall(r'\b(\d{1,3})\b', text)
        for num_str in numbers:
            try:
                num = int(num_str)
                if 1 <= num <= 999:
                    self.circuits.append(num)
            except ValueError:
                pass

    def _extract_rejection_patterns(self, text: str) -> None:
        """Learn patterns for rejection categories."""
        # Equipment: letters-digits pattern (FC-3, EQ-10)
        if re.match(r'^[A-Z]{2,4}-\d{1,3}', text):
            self.equipment_patterns['letter_dash_digit'] += 1

        # Fixture: alphanum + R + digits (B R012)
        if re.search(r'[A-Z0-9]+\s+R\d+', text):
            self.fixture_patterns['r_prefix'] += 1

        # Height: + prefix (+42", +48AFF)
        if text.startswith('+'):
            self.height_patterns['plus_prefix'] += 1

    def _get_pattern_structure(self, text: str) -> Optional[str]:
        """
        Convert text to a pattern structure.

        Returns: "letters", "letters+digits", "digit+letters", "digit+letters+digits", etc.
        """
        letters_only = re.match(r'^[A-Z]+$', text)
        letters_digits = re.match(r'^[A-Z]+\d+$', text)
        digit_letters = re.match(r'^\d+[A-Z]+$', text)
        digit_letters_digits = re.match(r'^\d+[A-Z]+\d+$', text)

        if letters_only:
            letter_count = len(text)
            return f"{letter_count}letters"
        elif letters_digits:
            letter_count = sum(1 for c in text if c.isalpha())
            digit_count = sum(1 for c in text if c.isdigit())
            return f"{letter_count}letters+{digit_count}digits"
        elif digit_letters:
            digit_count = sum(1 for c in text if c.isdigit())
            letter_count = sum(1 for c in text if c.isalpha())
            return f"{digit_count}digit+{letter_count}letters"
        elif digit_letters_digits:
            return "digit+letters+digits"
        else:
            return None

    def get_circuit_statistics(self) -> Optional[CircuitStatistics]:
        """Compute statistics about circuit numbers."""
        if not self.circuits:
            return None

        circuits_sorted = sorted(set(self.circuits))

        return CircuitStatistics(
            min_circuit=min(circuits_sorted),
            max_circuit=max(circuits_sorted),
            mean_circuit=sum(self.circuits) / len(self.circuits),
            median_circuit=circuits_sorted[len(circuits_sorted) // 2],
            circuits_seen=set(circuits_sorted),
            count=len(self.circuits)
        )

    def get_dominant_separator(self) -> str:
        """Return most common separator."""
        if not self.separators:
            return '-'
        return self.separators.most_common(1)[0][0]

    def get_panel_patterns(self, top_n: int = 5) -> list[tuple[str, int]]:
        """Return top N panel patterns."""
        return self.panel_patterns.most_common(top_n)


# ─────────────────────────────────────────────────────────────────────────────
# Pattern Learner
# ─────────────────────────────────────────────────────────────────────────────

class PatternLearner:
    """Learn patterns from analyzed statistics."""

    def __init__(self, config: Optional[LearnerConfig] = None):
        self.config = config or LearnerConfig()
        self.analyzer = StatisticalAnalyzer()

        # Learned patterns
        self.dominant_panel_pattern: Optional[PanelPatternTemplate] = None
        self.circuit_stats: Optional[CircuitStatistics] = None
        self.dominant_separator: str = '-'
        self.total_tokens: int = 0

    def fit(self, raw_texts: list[str]) -> bool:
        """
        Learn patterns from raw tokens.

        Returns: True if sufficient data to learn, False if insufficient.
        """
        logger.info(f"Learning patterns from {len(raw_texts)} tokens...")

        # Insufficient data
        if len(raw_texts) < self.config.min_samples:
            logger.warning(f"Only {len(raw_texts)} tokens; need {self.config.min_samples} to learn")
            return False

        self.total_tokens = len(raw_texts)

        # Analyze tokens
        self.analyzer.analyze_tokens(raw_texts)

        # Learn dominant patterns
        self._learn_panel_pattern()
        self._learn_circuit_statistics()
        self._learn_separator()

        logger.info(f"✓ Learned patterns: panel={self.dominant_panel_pattern}, "
                   f"circuits={self.circuit_stats}, sep='{self.dominant_separator}'")
        return True

    def _learn_panel_pattern(self) -> None:
        """Identify dominant panel naming pattern."""
        patterns = self.analyzer.get_panel_patterns(top_n=3)

        if not patterns:
            logger.warning("No panel patterns found; using hardcoded")
            return

        top_pattern, count = patterns[0]
        percentage = count / self.total_tokens

        if percentage < self.config.dominant_pattern_threshold:
            logger.warning(f"Panel pattern {top_pattern} only {percentage:.1%}; too weak")
            return

        # Convert pattern to regex
        regex = self._pattern_to_regex(top_pattern)

        self.dominant_panel_pattern = PanelPatternTemplate(
            pattern_description=top_pattern,
            regex_pattern=regex,
            frequency=count,
            percentage=percentage,
            examples=[]  # Would collect examples in real implementation
        )

        logger.info(f"Learned dominant panel pattern: {top_pattern} ({percentage:.1%})")

    def _learn_circuit_statistics(self) -> None:
        """Learn circuit number distribution."""
        self.circuit_stats = self.analyzer.get_circuit_statistics()

        if self.circuit_stats:
            logger.info(f"Learned circuit range: {self.circuit_stats.range} "
                       f"(n={self.circuit_stats.count})")

    def _learn_separator(self) -> None:
        """Learn dominant separator."""
        self.dominant_separator = self.analyzer.get_dominant_separator()
        logger.info(f"Learned dominant separator: '{self.dominant_separator}'")

    def _pattern_to_regex(self, pattern: str) -> str:
        """
        Convert pattern structure to regex.

        Examples:
          "2letters" → r"^[A-Z]{2}$"
          "2letters+2digits" → r"^[A-Z]{2}\d{2}$"
          "1digit+2letters" → r"^\d{1}[A-Z]{2}$"
        """
        # Parse pattern structure
        m = re.match(r'(\d+)(\w+)(?:\+(\d+)(\w+))?(?:\+(\d+)(\w+))?', pattern)
        if not m:
            return r"^[A-Z]+\d+$"  # Default

        parts = []
        for i in range(1, len(m.groups()) + 1, 2):
            count_str = m.group(i)
            type_str = m.group(i + 1)

            if not count_str or not type_str:
                continue

            count = int(count_str)
            if type_str == 'letters':
                parts.append(f'[A-Z]{{{count}}}')
            elif type_str == 'digits':
                parts.append(f'\\d{{{count}}}')
            elif type_str == 'letter':
                parts.append(f'[A-Z]{{{count}}}')
            elif type_str == 'digit':
                parts.append(f'\\d{{{count}}}')

        return '^' + ''.join(parts) + '$' if parts else r"^[A-Z]+\d+$"


# ─────────────────────────────────────────────────────────────────────────────
# Anomaly Detector
# ─────────────────────────────────────────────────────────────────────────────

class AnomalyDetector:
    """Detect outlier/anomalous tokens using learned patterns."""

    def __init__(self, learner: PatternLearner):
        self.learner = learner

    def detect_panel_anomaly(self, panel: str) -> float:
        """
        Score panel for anomaly.

        Returns: 0.0 (normal) to 1.0 (outlier)
        """
        if not self.learner.dominant_panel_pattern:
            return 0.0  # No pattern learned, assume normal

        try:
            regex = re.compile(self.learner.dominant_panel_pattern.regex_pattern)
            if regex.match(panel):
                return 0.0  # Matches learned pattern
            else:
                return 0.8  # Doesn't match (anomaly)
        except Exception:
            return 0.5

    def detect_circuit_anomaly(self, circuit: int) -> float:
        """
        Score circuit number for anomaly.

        Returns: 0.0 (normal) to 1.0 (outlier)
        """
        if not self.learner.circuit_stats:
            return 0.0  # No stats learned, assume normal

        min_c, max_c = self.learner.circuit_stats.range

        # Within learned range = normal
        if min_c <= circuit <= max_c:
            return 0.0

        # Outside range = anomaly (scored by distance)
        if circuit < min_c:
            distance = min_c - circuit
        else:
            distance = circuit - max_c

        # Score: distance normalized to range
        range_size = max_c - min_c + 1
        anomaly_score = min(1.0, distance / range_size)

        return anomaly_score

    def detect_pattern_anomaly(self, text: str, category: str) -> float:
        """
        Detect if text matches expected pattern for category.

        Args:
            text: The text token
            category: 'equipment', 'fixture', 'height', 'switch_leg', 'room_number'

        Returns: 0.0 (matches category) to 1.0 (doesn't match)
        """
        if category == 'equipment':
            # Expect: letters-digits pattern
            if re.match(r'^[A-Z]{2,4}-\d{1,3}', text):
                return 0.0
            elif re.match(r'^\d{1,3}[A-Z]{1}-\d{1,3}', text):
                return 0.0
            else:
                return 0.7  # Likely wrong category

        elif category == 'fixture':
            # Expect: alphanum + R + digits
            if re.search(r'[A-Z0-9]+\s+R\d+', text):
                return 0.0
            else:
                return 0.7

        elif category == 'height':
            # Expect: + prefix + digits
            if re.match(r'^\+\d+', text):
                return 0.0
            else:
                return 0.7

        elif category == 'switch_leg':
            # Expect: lowercase letters + optional digits
            if re.match(r'^[0-9]{0,2}[a-d]', text):
                return 0.0
            else:
                return 0.7

        elif category == 'room_number':
            # Expect: pure integer outside circuit range
            if text.isdigit():
                num = int(text)
                if self.learner.circuit_stats:
                    if num > self.learner.circuit_stats.max_circuit:
                        return 0.0
                return 0.5
            else:
                return 0.9

        return 0.5  # Unknown category


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

class PatternLearningEngine:
    """Main engine: learn patterns from tokens and detect anomalies."""

    def __init__(self, config: Optional[LearnerConfig] = None):
        self.config = config or LearnerConfig()
        self.learner = PatternLearner(self.config)
        self.detector = AnomalyDetector(self.learner)
        self.is_fitted = False

    def fit(self, raw_texts: list[str]) -> bool:
        """Learn patterns from raw tokens."""
        self.is_fitted = self.learner.fit(raw_texts)
        return self.is_fitted

    def get_panel_anomaly_score(self, panel: str) -> float:
        """Get anomaly score for a panel label (0.0=normal, 1.0=outlier)."""
        if not self.is_fitted:
            return 0.0
        return self.detector.detect_panel_anomaly(panel)

    def get_circuit_anomaly_score(self, circuit: int) -> float:
        """Get anomaly score for a circuit number (0.0=normal, 1.0=outlier)."""
        if not self.is_fitted:
            return 0.0
        return self.detector.detect_circuit_anomaly(circuit)

    def get_pattern_anomaly_score(self, text: str, category: str) -> float:
        """Get anomaly score for a text pattern in category (0.0=matches, 1.0=anomaly)."""
        if not self.is_fitted:
            return 0.0
        return self.detector.detect_pattern_anomaly(text, category)

    def should_flag_as_outlier(self, panel: str, circuit: int) -> bool:
        """
        Determine if token should be flagged as outlier.

        Returns: True if either panel or circuit has high anomaly score.
        """
        if not self.is_fitted:
            return False

        panel_anomaly = self.get_panel_anomaly_score(panel)
        circuit_anomaly = self.get_circuit_anomaly_score(circuit)

        return (panel_anomaly > self.config.panel_anomaly_threshold or
                circuit_anomaly > self.config.circuit_anomaly_threshold)

    def get_learned_circuit_range(self) -> Optional[tuple[int, int]]:
        """Return learned circuit min/max from data (instead of hardcoded 1-84)."""
        if self.learner.circuit_stats:
            return self.learner.circuit_stats.range
        return None

    def get_learned_separator(self) -> str:
        """Return learned dominant separator (instead of hardcoded -)."""
        return self.learner.dominant_separator

    def summary(self) -> str:
        """Return human-readable summary of learned patterns."""
        if not self.is_fitted:
            return "Engine not fitted (need minimum 10 tokens)"

        lines = [
            "═" * 80,
            "LEARNED PATTERNS SUMMARY",
            "═" * 80,
        ]

        if self.learner.dominant_panel_pattern:
            lines.append(f"Panel pattern: {self.learner.dominant_panel_pattern.pattern_description} "
                        f"({self.learner.dominant_panel_pattern.percentage:.1%})")

        if self.learner.circuit_stats:
            lines.append(f"Circuit range: {self.learner.circuit_stats.min_circuit}-"
                        f"{self.learner.circuit_stats.max_circuit} (n={self.learner.circuit_stats.count})")

        lines.append(f"Separator: '{self.learner.dominant_separator}'")
        lines.append("═" * 80)

        return "\n".join(lines)
