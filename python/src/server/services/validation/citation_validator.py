"""
Citation Validator for Reporting Agent.

Implements Task P0-43: Citation Validator for ReportingAgent [CRITICAL]

Validates that LLM-generated numbers match source citations and appends
footnotes for provenance tracking.

Example Output:
    "Mobile conversions: 1,234 [1] (-15% vs last week [2])"
    
    [1] Source: GA4 metric ID 101, Jan 5, 2026, mobile device
    [2] Source: GA4 metric ID 95, Dec 29, 2025, mobile device
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from pydantic import BaseModel, Field

from .number_extractor import NumberExtractor, ExtractedNumber
from agents.schemas.results import SourceCitation

logger = logging.getLogger(__name__)


class CitationMismatchError(Exception):
    """Raised when numbers don't match source citations."""
    
    def __init__(
        self,
        message: str,
        llm_value: float,
        citation_value: float,
        deviation_percent: float
    ):
        self.llm_value = llm_value
        self.citation_value = citation_value
        self.deviation_percent = deviation_percent
        super().__init__(message)


@dataclass
class CitationMatch:
    """Match between extracted number and source citation."""
    
    llm_value: float
    citation_value: float
    metric_name: str
    citation_id: int
    similarity_score: float
    deviation_percent: float
    is_valid: bool
    footnote_text: str


class CitationValidationReport(BaseModel):
    """Report from citation validation."""
    
    is_valid: bool
    total_numbers: int
    matched_numbers: int
    mismatches: List[Dict[str, Any]] = Field(default_factory=list)
    unmatched_numbers: List[Dict[str, Any]] = Field(default_factory=list)
    max_deviation_percent: float = 0.0
    
    @property
    def match_rate(self) -> float:
        """Calculate match rate (0-100%)."""
        if self.total_numbers == 0:
            return 100.0
        return (self.matched_numbers / self.total_numbers) * 100


class CitationValidator:
    """
    Validates LLM responses against source citations.
    
    Features:
    - Extracts numbers from LLM text
    - Matches numbers to source citations
    - Validates deviation <5%
    - Appends footnotes to text
    - Generates validation report
    
    Example:
        >>> validator = CitationValidator(tolerance_percent=5.0)
        >>> 
        >>> llm_response = "Mobile had 1,234 sessions"
        >>> citations = [SourceCitation(..., raw_json={"sessions": 1234})]
        >>> 
        >>> validated_text, report = await validator.validate_and_annotate(
        ...     llm_response, citations
        ... )
        >>> print(validated_text)
        "Mobile had 1,234 sessions [1]"
        >>> print(report.is_valid)
        True
    """
    
    DEFAULT_TOLERANCE = 5.0  # 5% deviation allowed
    
    def __init__(self, tolerance_percent: float = DEFAULT_TOLERANCE):
        """
        Initialize citation validator.
        
        Args:
            tolerance_percent: Maximum allowed deviation (default: 5%)
        """
        self.tolerance_percent = tolerance_percent
        self.extractor = NumberExtractor(context_window=5)
        
        logger.info(f"Citation validator initialized (tolerance={tolerance_percent}%)")
    
    async def validate_citations(
        self,
        llm_response: str,
        source_citations: List[SourceCitation],
        strict_mode: bool = False
    ) -> CitationValidationReport:
        """
        Validate LLM response against source citations.
        
        Args:
            llm_response: LLM-generated text
            source_citations: Source citations from RAG retrieval
            strict_mode: If True, raise exception on any mismatch
            
        Returns:
            CitationValidationReport with detailed results
            
        Raises:
            CitationMismatchError: If strict_mode=True and validation fails
        """
        logger.info(f"Validating {len(source_citations)} citations (strict={strict_mode})")
        
        # Extract numbers from LLM response
        extracted_numbers = self.extractor.extract(llm_response)
        
        # Build searchable citation database
        citation_values = self._build_citation_database(source_citations)
        
        # Match each extracted number to citations
        matches = []
        mismatches = []
        unmatched = []
        max_deviation = 0.0
        
        for extracted in extracted_numbers:
            match = self._match_to_citation(extracted, citation_values, source_citations)
            
            if match:
                if match.is_valid:
                    matches.append(match)
                else:
                    mismatches.append({
                        "llm_value": match.llm_value,
                        "citation_value": match.citation_value,
                        "metric_name": match.metric_name,
                        "deviation_percent": match.deviation_percent,
                        "citation_id": match.citation_id,
                    })
                    max_deviation = max(max_deviation, match.deviation_percent)
            else:
                unmatched.append({
                    "value": extracted.value,
                    "context": extracted.context,
                    "position": extracted.position,
                })
        
        # Build report
        is_valid = len(mismatches) == 0 and len(extracted_numbers) > 0
        
        report = CitationValidationReport(
            is_valid=is_valid,
            total_numbers=len(extracted_numbers),
            matched_numbers=len(matches),
            mismatches=mismatches,
            unmatched_numbers=unmatched,
            max_deviation_percent=max_deviation,
        )
        
        logger.info(
            f"Citation validation: {len(matches)}/{len(extracted_numbers)} matched, "
            f"{len(mismatches)} mismatches, max_deviation={max_deviation:.1f}%"
        )
        
        # Raise in strict mode
        if strict_mode and not is_valid:
            if mismatches:
                mismatch = mismatches[0]
                raise CitationMismatchError(
                    message=(
                        f"Citation mismatch: LLM says {mismatch['llm_value']} but "
                        f"citation has {mismatch['citation_value']} "
                        f"({mismatch['deviation_percent']:.1f}% deviation)"
                    ),
                    llm_value=mismatch['llm_value'],
                    citation_value=mismatch['citation_value'],
                    deviation_percent=mismatch['deviation_percent']
                )
        
        return report
    
    async def validate_and_annotate(
        self,
        llm_response: str,
        source_citations: List[SourceCitation]
    ) -> Tuple[str, CitationValidationReport]:
        """
        Validate and append citation footnotes to text.
        
        Args:
            llm_response: LLM-generated text
            source_citations: Source citations
            
        Returns:
            Tuple of (annotated_text, validation_report)
            
        Example:
            >>> text, report = await validator.validate_and_annotate(
            ...     "Mobile had 1,234 sessions",
            ...     citations
            ... )
            >>> print(text)
            "Mobile had 1,234 sessions [1]"
        """
        # Validate first
        report = await self.validate_citations(llm_response, source_citations)
        
        # Extract numbers
        extracted_numbers = self.extractor.extract(llm_response)
        
        # Build citation database
        citation_values = self._build_citation_database(source_citations)
        
        # Annotate text with footnotes
        annotated_text = llm_response
        offset = 0  # Track position shift from insertions
        
        for extracted in sorted(extracted_numbers, key=lambda x: x.position):
            match = self._match_to_citation(extracted, citation_values, source_citations)
            
            if match:
                # Insert footnote marker after number
                footnote = f" [{match.citation_id}]"
                insert_pos = extracted.position + len(extracted.raw_text) + offset
                
                annotated_text = (
                    annotated_text[:insert_pos] +
                    footnote +
                    annotated_text[insert_pos:]
                )
                
                offset += len(footnote)
        
        # Append footnote legend at end
        if source_citations:
            footnotes = self._generate_footnote_legend(source_citations)
            annotated_text += "\n\n" + footnotes
        
        return annotated_text, report
    
    def _build_citation_database(
        self,
        source_citations: List[SourceCitation]
    ) -> Dict[str, List[Tuple[float, int]]]:
        """
        Build searchable database of citation values.
        
        Args:
            source_citations: Source citations
            
        Returns:
            Dict mapping metric names to list of (value, citation_id) tuples
        """
        db = {}
        
        for idx, citation in enumerate(source_citations):
            for metric_name, value in citation.raw_json.items():
                try:
                    float_value = float(value)
                    
                    if metric_name not in db:
                        db[metric_name] = []
                    
                    db[metric_name].append((float_value, idx + 1))  # Citation ID starts at 1
                except (ValueError, TypeError):
                    continue
        
        return db
    
    def _match_to_citation(
        self,
        extracted: ExtractedNumber,
        citation_db: Dict[str, List[Tuple[float, int]]],
        source_citations: List[SourceCitation]
    ) -> Optional[CitationMatch]:
        """
        Match extracted number to source citation.
        
        Args:
            extracted: Extracted number with context
            citation_db: Citation database
            source_citations: Original citations
            
        Returns:
            CitationMatch or None if no match found
        """
        # Try to find metric in citation database
        metric_name = extracted.metric_name
        
        if not metric_name or metric_name not in citation_db:
            # Try alternative matching strategies
            for key in citation_db.keys():
                if key.lower() in extracted.context.lower():
                    metric_name = key
                    break
        
        if not metric_name or metric_name not in citation_db:
            return None
        
        # Find closest matching value in citations
        citation_values = citation_db[metric_name]
        
        best_match = None
        min_deviation = float('inf')
        
        for citation_value, citation_id in citation_values:
            deviation = self._calculate_deviation(extracted.value, citation_value)
            
            if deviation < min_deviation:
                min_deviation = deviation
                best_match = (citation_value, citation_id)
        
        if not best_match:
            return None
        
        citation_value, citation_id = best_match
        is_valid = min_deviation <= self.tolerance_percent
        
        # Get citation for footnote
        citation = source_citations[citation_id - 1]
        footnote = self._format_footnote(citation)
        
        return CitationMatch(
            llm_value=extracted.value,
            citation_value=citation_value,
            metric_name=metric_name,
            citation_id=citation_id,
            similarity_score=citation.similarity_score,
            deviation_percent=min_deviation,
            is_valid=is_valid,
            footnote_text=footnote,
        )
    
    def _calculate_deviation(self, llm_value: float, citation_value: float) -> float:
        """Calculate percentage deviation."""
        if citation_value == 0:
            return 100.0 if llm_value != 0 else 0.0
        
        return abs(llm_value - citation_value) / citation_value * 100
    
    def _format_footnote(self, citation: SourceCitation) -> str:
        """
        Format footnote text for citation.
        
        Args:
            citation: Source citation
            
        Returns:
            Formatted footnote text
            
        Example:
            "[1] Source: GA4 Property 123456789, Jan 5, 2026, metric_id=101"
        """
        return (
            f"Source: GA4 Property {citation.property_id}, "
            f"{citation.metric_date}, metric_id={citation.metric_id}, "
            f"similarity={citation.similarity_score:.2f}"
        )
    
    def _generate_footnote_legend(self, source_citations: List[SourceCitation]) -> str:
        """
        Generate footnote legend for all citations.
        
        Args:
            source_citations: List of source citations
            
        Returns:
            Formatted footnote legend
            
        Example:
            "---
            Sources:
            [1] GA4 Property 123, Jan 5, 2026 (similarity: 0.92)
            [2] GA4 Property 123, Jan 6, 2026 (similarity: 0.87)"
        """
        legend = "---\nSources:\n"
        
        for idx, citation in enumerate(source_citations):
            legend += f"[{idx + 1}] {self._format_footnote(citation)}\n"
        
        return legend.strip()

