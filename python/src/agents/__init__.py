"""
AI Agent system for GA4 analytics.

This package contains the Pydantic-AI based agent implementation,
replacing the CrewAI framework as per ADR-001.
"""

from .base_agent import BaseAgent, AgentRegistry
from .schemas import (
    DataFetchResult,
    EmbeddingResult,
    RetrievalResult,
    ReportResult,
    AgentStatus,
)

__all__ = [
    "BaseAgent",
    "AgentRegistry",
    "DataFetchResult",
    "EmbeddingResult",
    "RetrievalResult",
    "ReportResult",
    "AgentStatus",
]

