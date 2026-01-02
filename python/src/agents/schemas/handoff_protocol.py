"""
Agent Handoff Protocol Schema Definitions.

Implements Task P0-38: Agent Handoff Protocol Schema Definition

Defines explicit contracts for all agent-to-agent transitions with:
- Trigger conditions
- Timeout values
- Rollback strategies
- Payload schemas

This ensures deterministic agent workflow execution with proper error handling.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Type
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class TriggerCondition(str, Enum):
    """Conditions that trigger agent handoff."""
    SUCCESS = "success"
    CACHED = "cached"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"


class RollbackStrategy(str, Enum):
    """Rollback strategies when handoff fails."""
    CACHE_FALLBACK = "cache_fallback"
    RETRY = "retry"
    ABORT = "abort"
    SKIP_TO_NEXT = "skip_to_next"


class AgentHandoffProtocol(BaseModel):
    """
    Base protocol for agent-to-agent handoffs.
    
    Defines the contract for transitioning from one agent to another,
    including trigger conditions, timeouts, and fallback strategies.
    """
    
    from_agent: str = Field(
        description="Source agent name"
    )
    to_agent: str = Field(
        description="Destination agent name"
    )
    trigger_condition: TriggerCondition = Field(
        description="Condition that triggers this handoff"
    )
    timeout_ms: int = Field(
        gt=0,
        le=300000,  # Max 5 minutes
        description="Maximum time in milliseconds for handoff to complete"
    )
    rollback_strategy: RollbackStrategy = Field(
        description="Strategy to use if handoff fails"
    )
    payload_schema_version: str = Field(
        default="v1.0",
        description="Version of payload schema for backward compatibility"
    )
    retry_count: int = Field(
        default=0,
        ge=0,
        le=3,
        description="Number of retries attempted (0-3)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata for handoff"
    )


# =============================================================================
# Transition 1: DataFetcherAgent → EmbeddingAgent (Fresh Data)
# =============================================================================

class DataFetcherToEmbeddingHandoff(AgentHandoffProtocol):
    """
    Handoff from DataFetcherAgent to EmbeddingAgent.
    
    Triggered when: Fresh data is fetched from GA4 API
    Purpose: Generate embeddings for newly fetched data
    """
    
    from_agent: Literal["DataFetcherAgent"] = "DataFetcherAgent"
    to_agent: Literal["EmbeddingAgent"] = "EmbeddingAgent"
    trigger_condition: Literal[TriggerCondition.SUCCESS] = TriggerCondition.SUCCESS
    timeout_ms: int = Field(
        default=60000,  # 60 seconds
        description="Time to generate embeddings"
    )
    rollback_strategy: Literal[RollbackStrategy.RETRY] = RollbackStrategy.RETRY
    
    # Additional fields specific to this transition
    data_row_count: int = Field(
        description="Number of data rows to embed"
    )
    property_id: str = Field(
        description="GA4 property ID"
    )
    
    @field_validator("data_row_count")
    @classmethod
    def validate_row_count(cls, v: int) -> int:
        """Validate row count is reasonable."""
        if v > 10000:
            raise ValueError("Cannot embed more than 10,000 rows in single handoff")
        return v


# =============================================================================
# Transition 2: DataFetcherAgent → RagAgent (Cached Data)
# =============================================================================

class DataFetcherToRagHandoff(AgentHandoffProtocol):
    """
    Handoff from DataFetcherAgent to RagAgent.
    
    Triggered when: Data is retrieved from cache
    Purpose: Skip embedding generation, directly retrieve context
    """
    
    from_agent: Literal["DataFetcherAgent"] = "DataFetcherAgent"
    to_agent: Literal["RagAgent"] = "RagAgent"
    trigger_condition: Literal[TriggerCondition.CACHED] = TriggerCondition.CACHED
    timeout_ms: int = Field(
        default=30000,  # 30 seconds
        description="Time to retrieve cached context"
    )
    rollback_strategy: Literal[RollbackStrategy.CACHE_FALLBACK] = RollbackStrategy.CACHE_FALLBACK
    
    # Additional fields
    cache_key: str = Field(
        description="Redis cache key for cached data"
    )
    cache_age_seconds: int = Field(
        description="Age of cached data in seconds"
    )


# =============================================================================
# Transition 3: EmbeddingAgent → RagAgent (Embedding Complete)
# =============================================================================

class EmbeddingToRagHandoff(AgentHandoffProtocol):
    """
    Handoff from EmbeddingAgent to RagAgent.
    
    Triggered when: Embeddings generated successfully
    Purpose: Retrieve similar historical context using vector search
    """
    
    from_agent: Literal["EmbeddingAgent"] = "EmbeddingAgent"
    to_agent: Literal["RagAgent"] = "RagAgent"
    trigger_condition: Literal[TriggerCondition.SUCCESS] = TriggerCondition.SUCCESS
    timeout_ms: int = Field(
        default=45000,  # 45 seconds
        description="Time for vector similarity search"
    )
    rollback_strategy: Literal[RollbackStrategy.SKIP_TO_NEXT] = RollbackStrategy.SKIP_TO_NEXT
    
    # Additional fields
    embedding_quality_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Quality score of generated embeddings"
    )
    embedding_count: int = Field(
        description="Number of embeddings generated"
    )
    
    @field_validator("embedding_quality_score")
    @classmethod
    def validate_quality(cls, v: float) -> float:
        """Warn if quality score is low."""
        if v < 0.7:
            # Log warning but allow (will affect retrieval quality)
            pass
        return v


# =============================================================================
# Transition 4: RagAgent → ReportingAgent (Context Retrieved)
# =============================================================================

class RagToReportingHandoff(AgentHandoffProtocol):
    """
    Handoff from RagAgent to ReportingAgent.
    
    Triggered when: Relevant context retrieved from vector search
    Purpose: Generate structured report with insights
    """
    
    from_agent: Literal["RagAgent"] = "RagAgent"
    to_agent: Literal["ReportingAgent"] = "ReportingAgent"
    trigger_condition: Literal[TriggerCondition.SUCCESS] = TriggerCondition.SUCCESS
    timeout_ms: int = Field(
        default=90000,  # 90 seconds
        description="Time for LLM to generate report"
    )
    rollback_strategy: Literal[RollbackStrategy.SKIP_TO_NEXT] = RollbackStrategy.SKIP_TO_NEXT
    
    # Additional fields
    retrieval_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Average similarity score of retrieved documents"
    )
    context_document_count: int = Field(
        description="Number of context documents retrieved"
    )
    
    @field_validator("retrieval_confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure minimum confidence threshold."""
        if v < 0.5:
            raise ValueError(
                f"Retrieval confidence {v} too low (minimum: 0.5). "
                "Consider refetching data or using fallback."
            )
        return v


# =============================================================================
# Transition 5: Any Agent → FallbackAgent (Error Recovery)
# =============================================================================

class AnyAgentToFallbackHandoff(AgentHandoffProtocol):
    """
    Handoff from any agent to FallbackAgent.
    
    Triggered when: Agent execution fails or times out
    Purpose: Graceful degradation with cached data or partial results
    """
    
    from_agent: str  # Any agent can trigger fallback
    to_agent: Literal["FallbackAgent"] = "FallbackAgent"
    trigger_condition: Literal[TriggerCondition.FAILED, TriggerCondition.TIMEOUT] = TriggerCondition.FAILED
    timeout_ms: int = Field(
        default=15000,  # 15 seconds
        description="Quick fallback timeout"
    )
    rollback_strategy: Literal[RollbackStrategy.CACHE_FALLBACK] = RollbackStrategy.CACHE_FALLBACK
    
    # Additional fields
    error_message: str = Field(
        description="Error message from failed agent"
    )
    partial_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Partial result from failed agent (if any)"
    )
    failed_at_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the failure occurred"
    )


# =============================================================================
# Transition 6: ReportingAgent → Complete (Final Output)
# =============================================================================

class ReportingToCompleteHandoff(AgentHandoffProtocol):
    """
    Handoff from ReportingAgent to workflow completion.
    
    Triggered when: Report generated successfully
    Purpose: Finalize workflow and return result to user
    """
    
    from_agent: Literal["ReportingAgent"] = "ReportingAgent"
    to_agent: Literal["Complete"] = "Complete"
    trigger_condition: Literal[TriggerCondition.SUCCESS] = TriggerCondition.SUCCESS
    timeout_ms: int = Field(
        default=5000,  # 5 seconds
        description="Time for final cleanup and response formatting"
    )
    rollback_strategy: Literal[RollbackStrategy.ABORT] = RollbackStrategy.ABORT
    
    # Additional fields
    report_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall report confidence score"
    )
    chart_count: int = Field(
        ge=0,
        description="Number of charts in report"
    )
    metric_count: int = Field(
        ge=0,
        description="Number of metric cards in report"
    )


# =============================================================================
# Handoff Decision Tree
# =============================================================================

class HandoffDecisionTree(BaseModel):
    """
    Decision tree for agent handoff routing.
    
    Determines which handoff to use based on current state.
    """
    
    current_agent: str
    trigger_condition: TriggerCondition
    available_handoffs: List[Type[AgentHandoffProtocol]] = Field(
        default_factory=list
    )
    
    def get_next_handoff(
        self,
        agent_result: Dict[str, Any]
    ) -> Optional[AgentHandoffProtocol]:
        """
        Determine next handoff based on agent result.
        
        Args:
            agent_result: Result from current agent
        
        Returns:
            Appropriate handoff protocol, or None if workflow complete
        """
        # Decision logic based on current agent and result
        if self.current_agent == "DataFetcherAgent":
            if agent_result.get("cached"):
                return DataFetcherToRagHandoff(
                    cache_key=agent_result["cache_key"],
                    cache_age_seconds=agent_result["cache_age_seconds"]
                )
            else:
                return DataFetcherToEmbeddingHandoff(
                    data_row_count=len(agent_result.get("data", {}).get("rows", [])),
                    property_id=agent_result["property_id"]
                )
        
        elif self.current_agent == "EmbeddingAgent":
            return EmbeddingToRagHandoff(
                embedding_quality_score=agent_result["quality_score"],
                embedding_count=len(agent_result["embeddings"])
            )
        
        elif self.current_agent == "RagAgent":
            return RagToReportingHandoff(
                retrieval_confidence=agent_result["confidence"],
                context_document_count=len(agent_result["documents"])
            )
        
        elif self.current_agent == "ReportingAgent":
            return ReportingToCompleteHandoff(
                report_confidence=agent_result["confidence"],
                chart_count=len(agent_result.get("charts", [])),
                metric_count=len(agent_result.get("metrics", []))
            )
        
        return None


# =============================================================================
# Registry
# =============================================================================

HANDOFF_REGISTRY: Dict[str, Type[AgentHandoffProtocol]] = {
    "DataFetcherAgent->EmbeddingAgent": DataFetcherToEmbeddingHandoff,
    "DataFetcherAgent->RagAgent": DataFetcherToRagHandoff,
    "EmbeddingAgent->RagAgent": EmbeddingToRagHandoff,
    "RagAgent->ReportingAgent": RagToReportingHandoff,
    "*->FallbackAgent": AnyAgentToFallbackHandoff,
    "ReportingAgent->Complete": ReportingToCompleteHandoff,
}


def get_handoff_schema(from_agent: str, to_agent: str) -> Type[AgentHandoffProtocol]:
    """
    Get handoff schema for agent transition.
    
    Args:
        from_agent: Source agent name
        to_agent: Destination agent name
    
    Returns:
        Handoff protocol schema class
    
    Raises:
        KeyError: If transition not found in registry
    """
    key = f"{from_agent}->{to_agent}"
    
    if key in HANDOFF_REGISTRY:
        return HANDOFF_REGISTRY[key]
    
    # Check for wildcard fallback
    if f"*->{to_agent}" in HANDOFF_REGISTRY:
        return HANDOFF_REGISTRY[f"*->{to_agent}"]
    
    available = ", ".join(HANDOFF_REGISTRY.keys())
    raise KeyError(
        f"Handoff '{key}' not found in registry. "
        f"Available transitions: {available}"
    )

