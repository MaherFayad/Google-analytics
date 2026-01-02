"""
Transformation Diff API for Safe Upgrades.

Implements Task P0-50: Transformation Diff API for Safe Upgrades [HIGH]

Provides admin API to compare two transformation versions on sample data,
showing similarity scores and major deviations before deploying to production.

Features:
- Compare two transformation versions on sample data
- Calculate similarity scores using embeddings
- Identify major deviations (similarity <0.8)
- Provide deployment recommendations
- Export diff report as CSV

Example Use Case:
    Admin wants to update transformation logic from v1.0.0 to v1.1.0
    
    1. POST /api/v1/admin/transformation/compare
       {
         "version_a": "v1.0.0",
         "version_b": "v1.1.0",
         "sample_size": 100
       }
    
    2. Response shows:
       - average_similarity: 0.94 (94% similar)
       - major_deviations: 6 rows with similarity <0.8
       - recommendation: "SAFE_TO_DEPLOY"
    
    3. Admin reviews deviations, decides to deploy
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np

from ....database import get_session
from ....middleware.tenant import get_current_tenant_id, get_tenant_role
from ....models.ga4_metrics import GA4MetricsRaw
from ....services.embedding.embedding_service import EmbeddingService
from ....services.ga4.data_transformer import GA4DataTransformer
from ....core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/transformation", tags=["admin", "transformation"])


class DeploymentRecommendation(str, Enum):
    """Deployment recommendation based on similarity scores."""
    SAFE_TO_DEPLOY = "SAFE_TO_DEPLOY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNSAFE_HIGH_DEVIATION = "UNSAFE_HIGH_DEVIATION"


class TransformationCompareRequest(BaseModel):
    """Request model for transformation comparison."""
    
    version_a: str = Field(
        description="First transformation version (e.g., 'v1.0.0')",
        example="v1.0.0"
    )
    version_b: str = Field(
        description="Second transformation version (e.g., 'v1.1.0')",
        example="v1.1.0"
    )
    sample_size: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Number of random rows to compare (10-1000)"
    )
    tenant_id: Optional[str] = Field(
        default=None,
        description="Optional tenant ID to filter sample data"
    )


class TransformationDeviation(BaseModel):
    """Model for a single transformation deviation."""
    
    metric_id: int
    metric_date: str
    text_v1: str
    text_v2: str
    similarity: float = Field(ge=0.0, le=1.0)
    deviation_reason: str
    raw_metrics: Dict[str, Any]


class TransformationCompareResponse(BaseModel):
    """Response model for transformation comparison."""
    
    version_a: str
    version_b: str
    sample_size: int
    rows_compared: int
    average_similarity: float = Field(ge=0.0, le=1.0)
    median_similarity: float = Field(ge=0.0, le=1.0)
    min_similarity: float = Field(ge=0.0, le=1.0)
    max_similarity: float = Field(ge=0.0, le=1.0)
    major_deviations_count: int
    major_deviations: List[TransformationDeviation]
    recommendation: DeploymentRecommendation
    comparison_time_seconds: float
    timestamp: datetime


@router.post(
    "/compare",
    response_model=TransformationCompareResponse,
    summary="Compare transformation versions",
    description="Compare two transformation versions on sample data to assess deployment safety"
)
async def compare_transformation_versions(
    request: TransformationCompareRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    role: str = Depends(get_tenant_role),
    session: AsyncSession = Depends(get_session),
) -> TransformationCompareResponse:
    """
    Compare two transformation versions on sample data.
    
    This endpoint helps admins safely test transformation logic updates
    before deploying to production by:
    
    1. Fetching random sample of GA4 raw metrics
    2. Applying both transformation versions
    3. Generating embeddings for both outputs
    4. Computing cosine similarity
    5. Identifying major deviations (similarity <0.8)
    6. Providing deployment recommendation
    
    Args:
        request: Comparison parameters
        tenant_id: Current tenant ID (from JWT)
        role: User role (must be admin)
        session: Database session
        
    Returns:
        Comparison report with similarity scores and deviations
        
    Raises:
        HTTPException 403: If user is not admin
        HTTPException 404: If transformation versions not found
        HTTPException 500: If comparison fails
    """
    start_time = datetime.utcnow()
    
    # Verify admin role
    if role not in ["admin", "owner"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can compare transformation versions"
        )
    
    logger.info(
        f"Starting transformation comparison: {request.version_a} vs {request.version_b}",
        extra={
            "tenant_id": tenant_id,
            "sample_size": request.sample_size,
        }
    )
    
    try:
        # Fetch random sample of GA4 metrics
        sample_data = await _fetch_sample_data(
            session=session,
            sample_size=request.sample_size,
            tenant_id=request.tenant_id or tenant_id
        )
        
        if not sample_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No GA4 metrics data found for comparison"
            )
        
        logger.info(f"Fetched {len(sample_data)} rows for comparison")
        
        # Initialize services
        embedding_service = EmbeddingService(
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        transformer_v1 = GA4DataTransformer(version=request.version_a)
        transformer_v2 = GA4DataTransformer(version=request.version_b)
        
        # Compare transformations
        similarities = []
        deviations = []
        
        for row in sample_data:
            try:
                # Apply both transformations
                text_v1 = transformer_v1.transform_to_descriptive_text(
                    metric_date=row.metric_date,
                    dimension_context=row.dimension_context,
                    metric_values=row.metric_values
                )
                
                text_v2 = transformer_v2.transform_to_descriptive_text(
                    metric_date=row.metric_date,
                    dimension_context=row.dimension_context,
                    metric_values=row.metric_values
                )
                
                # Generate embeddings
                embedding_v1 = await embedding_service.generate_embedding(text_v1)
                embedding_v2 = await embedding_service.generate_embedding(text_v2)
                
                # Compute cosine similarity
                similarity = _cosine_similarity(embedding_v1, embedding_v2)
                similarities.append(similarity)
                
                # Check for major deviation
                if similarity < 0.8:
                    deviation_reason = _analyze_deviation(text_v1, text_v2, similarity)
                    
                    deviations.append(TransformationDeviation(
                        metric_id=row.id,
                        metric_date=row.metric_date.isoformat(),
                        text_v1=text_v1,
                        text_v2=text_v2,
                        similarity=similarity,
                        deviation_reason=deviation_reason,
                        raw_metrics={
                            "dimension_context": row.dimension_context,
                            "metric_values": row.metric_values
                        }
                    ))
            
            except Exception as e:
                logger.error(f"Error comparing row {row.id}: {e}", exc_info=True)
                continue
        
        # Calculate aggregate statistics
        avg_similarity = float(np.mean(similarities)) if similarities else 0.0
        median_similarity = float(np.median(similarities)) if similarities else 0.0
        min_similarity = float(np.min(similarities)) if similarities else 0.0
        max_similarity = float(np.max(similarities)) if similarities else 1.0
        
        # Determine recommendation
        recommendation = _get_deployment_recommendation(
            avg_similarity=avg_similarity,
            major_deviations_count=len(deviations)
        )
        
        # Sort deviations by similarity (lowest first)
        deviations.sort(key=lambda d: d.similarity)
        
        # Limit to top 10 deviations
        top_deviations = deviations[:10]
        
        # Calculate comparison time
        end_time = datetime.utcnow()
        comparison_time = (end_time - start_time).total_seconds()
        
        logger.info(
            f"Transformation comparison complete: "
            f"avg_similarity={avg_similarity:.2f}, "
            f"deviations={len(deviations)}, "
            f"recommendation={recommendation}, "
            f"time={comparison_time:.2f}s"
        )
        
        return TransformationCompareResponse(
            version_a=request.version_a,
            version_b=request.version_b,
            sample_size=request.sample_size,
            rows_compared=len(similarities),
            average_similarity=avg_similarity,
            median_similarity=median_similarity,
            min_similarity=min_similarity,
            max_similarity=max_similarity,
            major_deviations_count=len(deviations),
            major_deviations=top_deviations,
            recommendation=recommendation,
            comparison_time_seconds=comparison_time,
            timestamp=end_time
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transformation comparison failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transformation comparison failed: {str(e)}"
        )


async def _fetch_sample_data(
    session: AsyncSession,
    sample_size: int,
    tenant_id: str
) -> List[GA4MetricsRaw]:
    """
    Fetch random sample of GA4 metrics for comparison.
    
    Args:
        session: Database session
        sample_size: Number of rows to fetch
        tenant_id: Tenant ID to filter by
        
    Returns:
        List of GA4MetricsRaw rows
    """
    # Use PostgreSQL TABLESAMPLE for efficient random sampling
    # Note: This requires PostgreSQL 9.5+
    query = (
        select(GA4MetricsRaw)
        .where(GA4MetricsRaw.tenant_id == tenant_id)
        .order_by(func.random())
        .limit(sample_size)
    )
    
    result = await session.execute(query)
    rows = result.scalars().all()
    
    return list(rows)


def _cosine_similarity(embedding1: List[float], embedding2: List[float]) -> float:
    """
    Calculate cosine similarity between two embeddings.
    
    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector
        
    Returns:
        Cosine similarity (0-1)
    """
    vec1 = np.array(embedding1)
    vec2 = np.array(embedding2)
    
    # Compute cosine similarity
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    similarity = dot_product / (norm1 * norm2)
    
    # Clamp to [0, 1] range
    return float(max(0.0, min(1.0, similarity)))


def _analyze_deviation(text_v1: str, text_v2: str, similarity: float) -> str:
    """
    Analyze why two transformations deviated.
    
    Args:
        text_v1: Text from version 1
        text_v2: Text from version 2
        similarity: Similarity score
        
    Returns:
        Human-readable deviation reason
    """
    # Simple heuristics for common deviation reasons
    
    # Check for length differences
    len_diff = abs(len(text_v1) - len(text_v2))
    if len_diff > 100:
        return f"Significant length difference ({len_diff} characters)"
    
    # Check for numeric differences (rounding changes)
    import re
    numbers_v1 = set(re.findall(r'\d+\.?\d*', text_v1))
    numbers_v2 = set(re.findall(r'\d+\.?\d*', text_v2))
    
    if numbers_v1 != numbers_v2:
        return "Numeric value differences (possible rounding change)"
    
    # Check for word differences
    words_v1 = set(text_v1.lower().split())
    words_v2 = set(text_v2.lower().split())
    
    added_words = words_v2 - words_v1
    removed_words = words_v1 - words_v2
    
    if added_words or removed_words:
        return f"Wording changes (added: {len(added_words)}, removed: {len(removed_words)})"
    
    # Generic reason
    if similarity < 0.5:
        return "Major structural change"
    elif similarity < 0.7:
        return "Moderate transformation change"
    else:
        return "Minor transformation change"


def _get_deployment_recommendation(
    avg_similarity: float,
    major_deviations_count: int
) -> DeploymentRecommendation:
    """
    Determine deployment recommendation based on comparison results.
    
    Args:
        avg_similarity: Average similarity score
        major_deviations_count: Number of major deviations
        
    Returns:
        Deployment recommendation
    """
    # Recommendation logic
    if avg_similarity >= 0.9 and major_deviations_count <= 5:
        return DeploymentRecommendation.SAFE_TO_DEPLOY
    elif avg_similarity >= 0.8 and major_deviations_count <= 15:
        return DeploymentRecommendation.REVIEW_REQUIRED
    else:
        return DeploymentRecommendation.UNSAFE_HIGH_DEVIATION


@router.get(
    "/versions",
    summary="List available transformation versions",
    description="Get list of all available transformation versions"
)
async def list_transformation_versions(
    tenant_id: str = Depends(get_current_tenant_id),
    role: str = Depends(get_tenant_role),
    session: AsyncSession = Depends(get_session),
):
    """
    List all available transformation versions.
    
    Args:
        tenant_id: Current tenant ID
        role: User role (must be admin)
        session: Database session
        
    Returns:
        List of available transformation versions
        
    Raises:
        HTTPException 403: If user is not admin
    """
    # Verify admin role
    if role not in ["admin", "owner"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can list transformation versions"
        )
    
    # Query distinct transformation versions from audit log
    query = text("""
        SELECT DISTINCT transformation_version, COUNT(*) as usage_count
        FROM archon_ga4_transformation_audit
        WHERE tenant_id = :tenant_id
        GROUP BY transformation_version
        ORDER BY transformation_version DESC
    """)
    
    result = await session.execute(query, {"tenant_id": tenant_id})
    versions = result.fetchall()
    
    return {
        "versions": [
            {
                "version": row[0],
                "usage_count": row[1]
            }
            for row in versions
        ]
    }


@router.post(
    "/export-diff",
    summary="Export transformation diff as CSV",
    description="Export transformation comparison results as CSV file"
)
async def export_transformation_diff(
    request: TransformationCompareRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    role: str = Depends(get_tenant_role),
    session: AsyncSession = Depends(get_session),
):
    """
    Export transformation comparison as CSV.
    
    Args:
        request: Comparison parameters
        tenant_id: Current tenant ID
        role: User role (must be admin)
        session: Database session
        
    Returns:
        CSV file with comparison results
        
    Raises:
        HTTPException 403: If user is not admin
    """
    # Verify admin role
    if role not in ["admin", "owner"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can export transformation diffs"
        )
    
    # Get comparison results
    comparison = await compare_transformation_versions(
        request=request,
        tenant_id=tenant_id,
        role=role,
        session=session
    )
    
    # Generate CSV
    import csv
    import io
    from fastapi.responses import StreamingResponse
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "Metric ID",
        "Date",
        "Text V1",
        "Text V2",
        "Similarity",
        "Deviation Reason"
    ])
    
    # Write deviations
    for deviation in comparison.major_deviations:
        writer.writerow([
            deviation.metric_id,
            deviation.metric_date,
            deviation.text_v1,
            deviation.text_v2,
            f"{deviation.similarity:.4f}",
            deviation.deviation_reason
        ])
    
    # Write summary
    writer.writerow([])
    writer.writerow(["Summary"])
    writer.writerow(["Average Similarity", f"{comparison.average_similarity:.4f}"])
    writer.writerow(["Major Deviations", comparison.major_deviations_count])
    writer.writerow(["Recommendation", comparison.recommendation])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=transformation_diff_{request.version_a}_vs_{request.version_b}.csv"
        }
    )

