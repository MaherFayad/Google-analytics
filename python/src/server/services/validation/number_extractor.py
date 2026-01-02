"""
Number Extractor Utility.

Implements Task P0-11: Semantic Consistency Ground Truth Validator

Extracts numeric values and their context from natural language text.
Supports various number formats (1,234, 15%, +25%, -10%, etc.)
"""

import re
import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class NumberType(str, Enum):
    """Type of extracted number."""
    INTEGER = "integer"
    FLOAT = "float"
    PERCENTAGE = "percentage"
    CURRENCY = "currency"
    CHANGE = "change"  # e.g., +25%, -10%


@dataclass
class ExtractedNumber:
    """
    Represents a number extracted from text with context.
    
    Attributes:
        value: Numeric value
        raw_text: Original text (e.g., "1,234", "15%")
        number_type: Type of number
        context: Surrounding text (5 words before + after)
        position: Character position in original text
        metric_name: Inferred metric name (e.g., "sessions", "conversions")
    """
    value: float
    raw_text: str
    number_type: NumberType
    context: str
    position: int
    metric_name: Optional[str] = None


class NumberExtractor:
    """
    Extracts numbers from natural language text.
    
    Supports various formats:
    - Integers: 1234, 1,234
    - Floats: 12.34, 1,234.56
    - Percentages: 15%, +25%, -10%
    - Currency: $1,234, €50
    - Changes: increased by 25%, dropped 10%
    
    Example:
        >>> extractor = NumberExtractor()
        >>> text = "Mobile sessions increased to 1,234 (+15% vs last week)"
        >>> numbers = extractor.extract(text)
        >>> print(numbers[0].value, numbers[0].metric_name)
        1234.0 sessions
    """
    
    # Regex patterns for different number formats
    PATTERNS = {
        NumberType.PERCENTAGE: r'([+\-]?\d+(?:\.\d+)?)\s*%',
        NumberType.CURRENCY: r'[$€£¥]\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
        NumberType.FLOAT: r'\b(\d{1,3}(?:,\d{3})*\.\d+)\b',
        NumberType.INTEGER: r'\b(\d{1,3}(?:,\d{3})+)\b',  # With commas
        NumberType.CHANGE: r'([+\-]\s*\d+(?:\.\d+)?)\s*%?',
    }
    
    # Common GA4 metric keywords
    METRIC_KEYWORDS = {
        'sessions': ['session', 'visit', 'traffic'],
        'conversions': ['conversion', 'convert', 'goal'],
        'users': ['user', 'visitor', 'people'],
        'pageviews': ['pageview', 'page view', 'view'],
        'bounce_rate': ['bounce rate', 'bounce'],
        'engagement': ['engagement', 'engaged'],
        'revenue': ['revenue', 'sales', 'money'],
        'events': ['event', 'action'],
    }
    
    def __init__(self, context_window: int = 5):
        """
        Initialize number extractor.
        
        Args:
            context_window: Number of words to include before/after number
        """
        self.context_window = context_window
    
    def extract(self, text: str) -> List[ExtractedNumber]:
        """
        Extract all numbers from text with context.
        
        Args:
            text: Natural language text to extract from
            
        Returns:
            List of ExtractedNumber objects
            
        Example:
            >>> extractor = NumberExtractor()
            >>> text = "We had 1,234 sessions (up 15% from 1,072 last week)"
            >>> numbers = extractor.extract(text)
            >>> len(numbers)
            3
        """
        extracted = []
        
        # Extract each number type
        for number_type, pattern in self.PATTERNS.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in matches:
                try:
                    value = self._parse_number(match.group(1), number_type)
                    context = self._extract_context(text, match.start(), match.end())
                    metric_name = self._infer_metric_name(context)
                    
                    extracted.append(ExtractedNumber(
                        value=value,
                        raw_text=match.group(0),
                        number_type=number_type,
                        context=context,
                        position=match.start(),
                        metric_name=metric_name,
                    ))
                except ValueError as e:
                    logger.warning(f"Failed to parse number '{match.group(0)}': {e}")
                    continue
        
        # Sort by position
        extracted.sort(key=lambda x: x.position)
        
        # Remove duplicates (same value at nearby positions)
        extracted = self._remove_duplicates(extracted)
        
        return extracted
    
    def _parse_number(self, text: str, number_type: NumberType) -> float:
        """
        Parse number string to float.
        
        Args:
            text: Number string (e.g., "1,234", "15")
            number_type: Type of number
            
        Returns:
            Float value
        """
        # Remove commas and whitespace
        cleaned = text.replace(',', '').strip()
        
        # Remove currency symbols
        cleaned = re.sub(r'[$€£¥]', '', cleaned)
        
        # Parse to float
        try:
            return float(cleaned)
        except ValueError:
            raise ValueError(f"Cannot parse '{text}' as number")
    
    def _extract_context(self, text: str, start: int, end: int) -> str:
        """
        Extract context around number (N words before + after).
        
        Args:
            text: Full text
            start: Start position of number
            end: End position of number
            
        Returns:
            Context string
        """
        words = text.split()
        
        # Find word index for start position
        char_count = 0
        start_word_idx = 0
        for i, word in enumerate(words):
            if char_count >= start:
                start_word_idx = i
                break
            char_count += len(word) + 1  # +1 for space
        
        # Extract context window
        context_start = max(0, start_word_idx - self.context_window)
        context_end = min(len(words), start_word_idx + self.context_window + 1)
        
        return ' '.join(words[context_start:context_end])
    
    def _infer_metric_name(self, context: str) -> Optional[str]:
        """
        Infer metric name from context.
        
        Args:
            context: Context string around number
            
        Returns:
            Metric name or None
            
        Example:
            >>> extractor._infer_metric_name("mobile sessions increased to")
            'sessions'
        """
        context_lower = context.lower()
        
        for metric_name, keywords in self.METRIC_KEYWORDS.items():
            for keyword in keywords:
                if keyword in context_lower:
                    return metric_name
        
        return None
    
    def _remove_duplicates(self, numbers: List[ExtractedNumber]) -> List[ExtractedNumber]:
        """
        Remove duplicate numbers (same value at nearby positions).
        
        For example, "1,234" and "1234" both represent the same number.
        
        Args:
            numbers: List of extracted numbers
            
        Returns:
            Deduplicated list
        """
        if not numbers:
            return []
        
        unique = [numbers[0]]
        
        for num in numbers[1:]:
            # Check if this is a duplicate of the last number
            last = unique[-1]
            
            # Same value and close position = duplicate
            if (abs(num.value - last.value) < 0.01 and 
                abs(num.position - last.position) < 20):
                continue
            
            unique.append(num)
        
        return unique
    
    def extract_by_metric(self, text: str, metric_name: str) -> List[ExtractedNumber]:
        """
        Extract numbers for a specific metric.
        
        Args:
            text: Natural language text
            metric_name: Metric to filter by (e.g., "sessions")
            
        Returns:
            List of numbers related to that metric
            
        Example:
            >>> text = "1,234 sessions with 56 conversions"
            >>> extractor.extract_by_metric(text, "sessions")
            [ExtractedNumber(value=1234, metric_name='sessions')]
        """
        all_numbers = self.extract(text)
        return [n for n in all_numbers if n.metric_name == metric_name]

