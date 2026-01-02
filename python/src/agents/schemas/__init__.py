"""
Agent result schemas and contracts.

This module defines typed contracts for agent-to-agent communication,
ensuring type safety and runtime validation across the agent pipeline.

Implements Task P0-22: Agent Result Schema Registry & Validation
Implements Task P0-21: Chart Data Schema Specification & Validation
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
)

# Import enhanced chart schemas (Task P0-21)
from .charts import (
    ChartConfig,
    LineChartConfig,
    BarChartConfig,
    PieChartConfig,
    AreaChartConfig,
    ChartDataPoint,
    PieChartDataPoint,
    MetricCard,
    validate_chart_data,
)

__all__ = [
    # Agent result schemas
    "DataFetchResult",
    "EmbeddingResult",
    "RetrievalResult",
    "ReportResult",
    "AgentStatus",
    "SourceCitation",
    # Chart schemas (Task P0-21)
    "ChartConfig",
    "LineChartConfig",
    "BarChartConfig",
    "PieChartConfig",
    "AreaChartConfig",
    "ChartDataPoint",
    "PieChartDataPoint",
    "MetricCard",
    "validate_chart_data",
    # Schema registry
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

