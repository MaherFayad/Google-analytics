"""
Typed result contracts for agent-to-agent communication.

These Pydantic V2 models define the data contracts between agents,
enabling compile-time type checking and runtime validation.

Implements Task P0-22: Agent Result Schema Registry & Validation

Note: Chart schemas moved to charts.py (Task P0-21) for better organization.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

# Import chart schemas from dedicated module (Task P0-21)
from .charts import ChartConfig, ChartDataPoint, MetricCard


class AgentStatus(BaseModel):
    """Status information for agent execution."""
    
    agent_name: str
    status: Literal["pending", "running", "success", "failed", "cached"]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    @property
    def duration_ms(self) -> Optional[int]:
        """Calculate execution duration in milliseconds."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None


class DataFetchResult(BaseModel):
    """Result from DataFetcherAgent - GA4 data retrieval."""
    
    status: Literal["success", "cached", "failed"]
    data: Dict[str, Any] = Field(
        description="Raw GA4 API response data (dimensions, metrics, rows)"
    )
    cached: bool = Field(
        default=False,
        description="Whether data was retrieved from cache"
    )
    tenant_id: str = Field(
        description="Tenant ID for multi-tenant isolation"
    )
    property_id: str = Field(
        description="GA4 property ID"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When data was fetched"
    )
    source: str = Field(
        default="ga4_api",
        description="Data source (ga4_api, cache, mock)"
    )
    quota_consumed: int = Field(
        default=1,
        description="Number of GA4 API quota tokens consumed"
    )
    
    @field_validator("data")
    @classmethod
    def validate_data_structure(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure data has required GA4 response structure."""
        if "rows" not in v and "dimensionHeaders" not in v:
            raise ValueError("GA4 data must contain 'rows' or 'dimensionHeaders'")
        return v


class EmbeddingResult(BaseModel):
    """Result from EmbeddingAgent - vector embeddings generation."""
    
    embeddings: List[List[float]] = Field(
        description="Generated embeddings (1536-dim for text-embedding-3-small)"
    )
    quality_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Embedding quality score (0-1, based on validation checks)"
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="List of validation errors (NaN, zero vectors, etc.)"
    )
    dimension: int = Field(
        default=1536,
        description="Embedding dimension (must match pgvector index)"
    )
    model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model used"
    )
    tenant_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    @field_validator("embeddings")
    @classmethod
    def validate_embeddings(cls, v: List[List[float]]) -> List[List[float]]:
        """Validate embedding dimensions and values."""
        for idx, embedding in enumerate(v):
            if len(embedding) != 1536:
                raise ValueError(
                    f"Embedding {idx} has {len(embedding)} dimensions, expected 1536"
                )
            if all(x == 0 for x in embedding):
                raise ValueError(f"Embedding {idx} is a zero vector")
        return v


class SourceCitation(BaseModel):
    """Source citation for data provenance tracking."""
    
    metric_id: int = Field(
        description="ID from ga4_metrics_raw table"
    )
    property_id: str
    metric_date: str = Field(
        description="Date of metric (YYYY-MM-DD)"
    )
    raw_json: Dict[str, Any] = Field(
        description="Original GA4 metric values"
    )
    similarity_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Vector similarity score (0-1)"
    )


class RetrievalResult(BaseModel):
    """Result from RagAgent - vector similarity search."""
    
    documents: List[str] = Field(
        description="Retrieved document texts (descriptive summaries)"
    )
    citations: List[SourceCitation] = Field(
        description="Source citations for provenance tracking"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Average similarity score of retrieved documents"
    )
    tenant_id: str
    query_embedding: List[float] = Field(
        description="Query embedding used for search"
    )
    match_count: int = Field(
        default=5,
        description="Number of documents retrieved"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    @field_validator("documents", "citations")
    @classmethod
    def validate_lengths_match(cls, v, info):
        """Ensure documents and citations have same length."""
        if info.field_name == "citations":
            documents = info.data.get("documents", [])
            if len(v) != len(documents):
                raise ValueError(
                    f"Citations count ({len(v)}) must match documents count ({len(documents)})"
                )
        return v


class ReportResult(BaseModel):
    """Result from ReportingAgent - structured report generation."""
    
    answer: str = Field(
        description="Natural language answer to user query"
    )
    charts: List[Any] = Field(
        default_factory=list,
        description="Chart configurations for visualization (LineChartConfig, BarChartConfig, etc.)"
    )
    metrics: List[MetricCard] = Field(
        default_factory=list,
        description="Key metric cards"
    )
    citations: List[SourceCitation] = Field(
        default_factory=list,
        description="Source citations for data provenance"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall report confidence score"
    )
    tenant_id: str
    query: str = Field(description="Original user query")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Mobile conversions increased 21.7% last week...",
                "charts": [
                    {
                        "type": "line",
                        "title": "Sessions Over Time",
                        "x_label": "Date",
                        "y_label": "Sessions",
                        "data": [
                            {"x": "2025-01-01", "y": 1234},
                            {"x": "2025-01-02", "y": 1456}
                        ]
                    }
                ],
                "metrics": [
                    {
                        "label": "Sessions",
                        "value": "12,450",
                        "change": "+21.7%",
                        "trend": "up"
                    }
                ],
                "confidence": 0.92,
                "tenant_id": "uuid",
                "query": "Show mobile conversions last week"
            }
        }

