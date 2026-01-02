"""
Agent result schemas and contracts.

This module defines typed contracts for agent-to-agent communication,
ensuring type safety and runtime validation across the agent pipeline.

Implements Task P0-22: Agent Result Schema Registry & Validation
"""

from typing import Type, Dict
from pydantic import BaseModel

from .results import (
    DataFetchResult,
    EmbeddingResult,
    RetrievalResult,
    ReportResult,
    AgentStatus,
    SourceCitation,
    ChartConfig,
    MetricCard,
    ChartDataPoint,
)

__all__ = [
    "DataFetchResult",
    "EmbeddingResult",
    "RetrievalResult",
    "ReportResult",
    "AgentStatus",
    "SourceCitation",
    "ChartConfig",
    "MetricCard",
    "ChartDataPoint",
    "AGENT_SCHEMA_REGISTRY",
    "get_schema_for_agent",
]


# Schema Registry: Maps agent names to their result schemas
AGENT_SCHEMA_REGISTRY: Dict[str, Type[BaseModel]] = {
    "DataFetcherAgent": DataFetchResult,
    "EmbeddingAgent": EmbeddingResult,
    "RagAgent": RetrievalResult,
    "ReportingAgent": ReportResult,
}


def get_schema_for_agent(agent_name: str) -> Type[BaseModel]:
    """
    Get Pydantic schema for agent by name.
    
    Args:
        agent_name: Name of agent (e.g., "DataFetcherAgent")
    
    Returns:
        Pydantic model class for agent's result
    
    Raises:
        KeyError: If agent name not found in registry
    
    Example:
        schema = get_schema_for_agent("DataFetcherAgent")
        # Returns: DataFetchResult
    """
    if agent_name not in AGENT_SCHEMA_REGISTRY:
        available_agents = ", ".join(AGENT_SCHEMA_REGISTRY.keys())
        raise KeyError(
            f"Agent '{agent_name}' not found in schema registry. "
            f"Available agents: {available_agents}"
        )
    
    return AGENT_SCHEMA_REGISTRY[agent_name]

