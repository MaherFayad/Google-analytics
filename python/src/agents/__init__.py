"""
AI Agent system for GA4 analytics.

This package contains the Pydantic-AI based agent implementation,
replacing the CrewAI framework as per ADR-001.
"""

from .base_agent import BaseAgent, AgentRegistry
from .data_fetcher_agent import DataFetcherAgent
from .embedding_agent import EmbeddingAgent
from .rag_agent import RagAgent
from .reporting_agent import ReportingAgent
from .orchestrator_agent import OrchestratorAgent
from .orchestrator_with_handoff import EnhancedOrchestratorAgent
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
    "DataFetcherAgent",
    "EmbeddingAgent",
    "RagAgent",
    "ReportingAgent",
    "OrchestratorAgent",
    "EnhancedOrchestratorAgent",
    "DataFetchResult",
    "EmbeddingResult",
    "RetrievalResult",
    "ReportResult",
    "AgentStatus",
]

