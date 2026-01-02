"""
Agent result schemas and contracts.

This module defines typed contracts for agent-to-agent communication,
ensuring type safety and runtime validation across the agent pipeline.
"""

from .results import (
    DataFetchResult,
    EmbeddingResult,
    RetrievalResult,
    ReportResult,
    AgentStatus,
)

__all__ = [
    "DataFetchResult",
    "EmbeddingResult",
    "RetrievalResult",
    "ReportResult",
    "AgentStatus",
]

