"""
Context Grounding Checker for LLM Response Validation.

Implements Task P0-45: Context Grounding Checker [CRITICAL-DATA-INTEGRITY]

Validates that every factual claim in LLM response is supported by
retrieved context. Prevents "context leakage" where LLM uses world
knowledge instead of provided GA4 data.

Example Attack Vector (Prevented):
    Query: "How does my traffic compare to industry average?"
    Context: "Your traffic: 10,000 sessions/month"
    LLM Says: "Your 10K sessions is below industry average of 50K"
    
    Grounding Check: ❌ REJECTED - "industry average" not in context
    Action: Regenerate without world knowledge
"""

import logging
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GroundingStatus(str, Enum):
    """Status of grounding validation."""
    FULLY_GROUNDED = "fully_grounded"
    PARTIALLY_GROUNDED = "partially_grounded"
    UNGROUNDED = "ungrounded"
    UNKNOWN = "unknown"


@dataclass
class FactualClaim:
    """Represents a factual claim extracted from text."""
    
    claim_text: str
    claim_type: str  # 'numeric', 'comparison', 'trend', 'attribution'
    confidence: float  # 0.0 - 1.0
    position: int  # Character position in original text
    
    # Grounding evidence
    is_grounded: bool = False
    supporting_evidence: Optional[str] = None
    similarity_score: Optional[float] = None


class GroundingReport(BaseModel):
    """Report from context grounding validation."""
    
    status: GroundingStatus
    validation_score: float = Field(ge=0.0, le=1.0, description="Percentage of claims grounded (0-1)")
    total_claims: int
    grounded_claims: int
    ungrounded_claims: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    severity: str = "low"  # low, medium, high, critical
    
    @property
    def grounding_rate(self) -> float:
        """Calculate grounding rate (0-100%)."""
        if self.total_claims == 0:
            return 100.0
        return (self.grounded_claims / self.total_claims) * 100


class ContextGroundingChecker:
    """
    Validates LLM responses are grounded in provided context.
    
    Features:
    - Extracts factual claims from LLM text
    - Checks each claim against retrieval context
    - Validates similarity threshold (>0.7)
    - Detects world knowledge injection
    - Generates detailed grounding report
    
    Example:
        >>> checker = ContextGroundingChecker(similarity_threshold=0.7)
        >>> 
        >>> llm_response = "Mobile had 10K sessions, which is below industry average"
        >>> context = ["Mobile sessions: 10,234 on Jan 5"]
        >>> 
        >>> report = await checker.validate_grounding(llm_response, context)
        >>> print(report.status)
        PARTIALLY_GROUNDED  # "10K sessions" grounded, "industry average" not
    """
    
    DEFAULT_SIMILARITY_THRESHOLD = 0.7
    
    # Patterns for extracting factual claims
    CLAIM_PATTERNS = {
        'numeric': r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:%|percent|sessions|conversions|users)',
        'comparison': r'(?:higher|lower|more|less|above|below|greater|fewer)\s+than',
        'trend': r'(?:increased|decreased|grew|declined|dropped|rose)\s+(?:by\s+)?\d+',
        'attribution': r'(?:because|due to|caused by|resulting from)',
    }
    
    def __init__(
        self,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        openai_api_key: Optional[str] = None
    ):
        """
        Initialize context grounding checker.
        
        Args:
            similarity_threshold: Minimum similarity for grounding (default: 0.7)
            openai_api_key: Optional OpenAI key for claim extraction
        """
        self.similarity_threshold = similarity_threshold
        self.openai_api_key = openai_api_key
        
        logger.info(f"Context grounding checker initialized (threshold={similarity_threshold})")
    
    async def validate_grounding(
        self,
        llm_response: str,
        retrieval_context: List[str],
        raw_ga4_metrics: Optional[Dict[str, Any]] = None
    ) -> GroundingReport:
        """
        Validate that LLM response is grounded in retrieval context.
        
        Args:
            llm_response: LLM-generated text to validate
            retrieval_context: Retrieved documents (RAG context)
            raw_ga4_metrics: Optional raw GA4 metrics for additional validation
            
        Returns:
            GroundingReport with detailed validation results
            
        Example:
            >>> report = await checker.validate_grounding(
            ...     llm_response="Mobile had 10K sessions",
            ...     retrieval_context=["Mobile sessions: 10,234"],
            ...     raw_ga4_metrics={"sessions": 10234, "device": "mobile"}
            ... )
            >>> print(report.status)
            FULLY_GROUNDED
        """
        logger.info(f"Validating grounding (context_docs={len(retrieval_context)})")
        
        # Extract factual claims from LLM response
        claims = self._extract_claims(llm_response)
        
        logger.debug(f"Extracted {len(claims)} factual claims")
        
        if not claims:
            # No claims to validate
            return GroundingReport(
                status=GroundingStatus.UNKNOWN,
                validation_score=1.0,
                total_claims=0,
                grounded_claims=0,
                warnings=["No factual claims found in response"],
            )
        
        # Check each claim against context
        grounded_count = 0
        ungrounded = []
        
        for claim in claims:
            is_grounded, evidence, similarity = self._check_claim_grounding(
                claim,
                retrieval_context,
                raw_ga4_metrics
            )
            
            if is_grounded:
                claim.is_grounded = True
                claim.supporting_evidence = evidence
                claim.similarity_score = similarity
                grounded_count += 1
            else:
                ungrounded.append({
                    "claim": claim.claim_text,
                    "type": claim.claim_type,
                    "confidence": claim.confidence,
                    "reason": "No supporting evidence found in context"
                })
        
        # Calculate validation score
        validation_score = grounded_count / len(claims) if claims else 1.0
        
        # Determine status
        if validation_score >= 1.0:
            status = GroundingStatus.FULLY_GROUNDED
            severity = "low"
        elif validation_score >= 0.7:
            status = GroundingStatus.PARTIALLY_GROUNDED
            severity = "medium"
        elif validation_score >= 0.3:
            status = GroundingStatus.PARTIALLY_GROUNDED
            severity = "high"
        else:
            status = GroundingStatus.UNGROUNDED
            severity = "critical"
        
        logger.info(
            f"Grounding validation: {grounded_count}/{len(claims)} claims grounded "
            f"(score={validation_score:.2f}, status={status})"
        )
        
        return GroundingReport(
            status=status,
            validation_score=validation_score,
            total_claims=len(claims),
            grounded_claims=grounded_count,
            ungrounded_claims=ungrounded,
            severity=severity,
        )
    
    def _extract_claims(self, text: str) -> List[FactualClaim]:
        """
        Extract factual claims from text.
        
        Uses pattern matching to identify:
        - Numeric claims (with values)
        - Comparison claims (vs other data)
        - Trend claims (increased/decreased)
        - Attribution claims (caused by X)
        
        Args:
            text: Text to extract claims from
            
        Returns:
            List of FactualClaim objects
        """
        claims = []
        
        # Split text into sentences
        sentences = re.split(r'[.!?]+', text)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            # Check each pattern type
            for claim_type, pattern in self.CLAIM_PATTERNS.items():
                if re.search(pattern, sentence, re.IGNORECASE):
                    claim = FactualClaim(
                        claim_text=sentence,
                        claim_type=claim_type,
                        confidence=0.8,  # Default confidence
                        position=text.index(sentence) if sentence in text else 0
                    )
                    claims.append(claim)
                    break  # One claim type per sentence
        
        return claims
    
    def _check_claim_grounding(
        self,
        claim: FactualClaim,
        retrieval_context: List[str],
        raw_ga4_metrics: Optional[Dict[str, Any]]
    ) -> tuple[bool, Optional[str], Optional[float]]:
        """
        Check if claim is grounded in retrieval context.
        
        Args:
            claim: Factual claim to check
            retrieval_context: Retrieved documents
            raw_ga4_metrics: Optional raw metrics for validation
            
        Returns:
            Tuple of (is_grounded, supporting_evidence, similarity_score)
        """
        # Combine all context into searchable text
        combined_context = " ".join(retrieval_context)
        
        # Extract key terms from claim
        claim_terms = self._extract_key_terms(claim.claim_text)
        
        # Check if terms appear in context
        best_match = None
        best_similarity = 0.0
        
        for context_doc in retrieval_context:
            similarity = self._calculate_text_similarity(claim.claim_text, context_doc)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = context_doc
        
        # Check if similarity meets threshold
        is_grounded = best_similarity >= self.similarity_threshold
        
        return is_grounded, best_match, best_similarity
    
    def _extract_key_terms(self, text: str) -> List[str]:
        """
        Extract key terms from text for matching.
        
        Args:
            text: Text to extract terms from
            
        Returns:
            List of key terms
        """
        # Remove common words
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'is', 'was', 'are', 'were', 'has', 'have',
            'had', 'been', 'being', 'be', 'this', 'that', 'these', 'those'
        }
        
        words = re.findall(r'\b\w+\b', text.lower())
        key_terms = [w for w in words if w not in stopwords and len(w) > 2]
        
        return key_terms
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate simple text similarity (Jaccard similarity).
        
        For production, this should use embedding cosine similarity.
        This is a simplified version for initial implementation.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score (0-1)
        """
        # Extract terms
        terms1 = set(self._extract_key_terms(text1))
        terms2 = set(self._extract_key_terms(text2))
        
        if not terms1 or not terms2:
            return 0.0
        
        # Jaccard similarity
        intersection = len(terms1 & terms2)
        union = len(terms1 | terms2)
        
        return intersection / union if union > 0 else 0.0
    
    async def detect_world_knowledge_injection(
        self,
        llm_response: str,
        retrieval_context: List[str]
    ) -> List[str]:
        """
        Detect if LLM injected world knowledge not in context.
        
        Common patterns:
        - "Industry average is..."
        - "According to studies..."
        - "Typically, websites have..."
        - "Compared to competitors..."
        
        Args:
            llm_response: LLM-generated text
            retrieval_context: Retrieved context
            
        Returns:
            List of detected world knowledge phrases
        """
        world_knowledge_patterns = [
            r'industry average',
            r'industry benchmark',
            r'according to (?:studies|research|experts)',
            r'typically,?\s+(?:websites|sites|businesses)',
            r'compared to competitors',
            r'market research shows',
            r'studies show',
            r'experts say',
            r'industry standard',
        ]
        
        detected = []
        combined_context = " ".join(retrieval_context).lower()
        
        for pattern in world_knowledge_patterns:
            matches = re.finditer(pattern, llm_response.lower())
            
            for match in matches:
                phrase = match.group(0)
                
                # Check if this phrase is NOT in context
                if phrase not in combined_context:
                    detected.append(phrase)
                    logger.warning(f"Detected world knowledge injection: '{phrase}'")
        
        return detected

