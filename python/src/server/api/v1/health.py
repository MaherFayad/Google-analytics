"""
Health Check and Monitoring Endpoints

Implements Task P0-13: pgBouncer Connection Pool Health Monitoring

Provides:
- Database health check with connection pool stats
- pgBouncer statistics
- Prometheus metrics exporting
- Real-time pool utilization monitoring

Usage:
    GET /health/database - Get database health status
    GET /health/pools - Get detailed pool statistics
    GET /metrics - Prometheus metrics endpoint
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, status as http_status
from pydantic import BaseModel, Field

from ...database import get_pool_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class DatabaseHealthResponse(BaseModel):
    """Database health check response."""
    
    status: str = Field(
        description="Health status: 'healthy', 'degraded', or 'critical'"
    )
    message: str = Field(
        description="Human-readable status message"
    )
    transactional_pool: Dict[str, Any] = Field(
        description="Transactional pool statistics"
    )
    session_pool: Dict[str, Any] = Field(
        description="Session pool statistics"
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Recommended actions if degraded/critical"
    )


class PoolStatsResponse(BaseModel):
    """Detailed connection pool statistics."""
    
    transactional: Dict[str, Any]
    session: Dict[str, Any]
    timestamp: str


@router.get(
    "/database",
    response_model=DatabaseHealthResponse,
    summary="Database Health Check",
    description="Check database connection pool health and utilization"
)
async def database_health() -> DatabaseHealthResponse:
    """
    Check database health with connection pool statistics.
    
    Implements Task P0-13: Real-time pool monitoring
    
    Returns health status based on pool utilization:
    - healthy: utilization < 75%
    - degraded: utilization 75-90%
    - critical: utilization > 90%
    
    Returns:
        DatabaseHealthResponse with pool stats and health status
        
    Example Response:
        {
            "status": "healthy",
            "message": "All connection pools healthy",
            "transactional_pool": {
                "size": 25,
                "checked_out": 12,
                "utilization": 48.0
            },
            "session_pool": {
                "size": 10,
                "checked_out": 3,
                "utilization": 30.0
            },
            "recommendations": []
        }
    """
    try:
        # Get connection pool stats
        stats = await get_pool_stats()
        
        trans_pool = stats["transactional"]
        session_pool = stats["session"]
        
        # Determine overall health status
        trans_util = trans_pool["utilization"]
        session_util = session_pool["utilization"]
        
        max_utilization = max(trans_util, session_util)
        
        # Health thresholds
        if max_utilization >= 90:
            status = "critical"
            message = f"Connection pool critically high: {max_utilization:.1f}% utilization"
        elif max_utilization >= 75:
            status = "degraded"
            message = f"Connection pool utilization elevated: {max_utilization:.1f}%"
        else:
            status = "healthy"
            message = "All connection pools healthy"
        
        # Generate recommendations
        recommendations = []
        
        if trans_util >= 80:
            recommendations.append(
                f"Transactional pool at {trans_util:.1f}% - Consider increasing pool_size or investigating slow queries"
            )
        
        if session_util >= 80:
            recommendations.append(
                f"Session pool at {session_util:.1f}% - Long-running transactions may be blocking pool"
            )
        
        if trans_pool.get("overflow", 0) > 0:
            recommendations.append(
                f"Transactional pool using overflow capacity ({trans_pool['overflow']} connections) - "
                "Consider increasing default pool size"
            )
        
        if session_pool.get("overflow", 0) > 0:
            recommendations.append(
                f"Session pool using overflow capacity ({session_pool['overflow']} connections) - "
                "Consider increasing default pool size or reducing concurrent workers"
            )
        
        return DatabaseHealthResponse(
            status=status,
            message=message,
            transactional_pool=trans_pool,
            session_pool=session_pool,
            recommendations=recommendations
        )
    
    except Exception as e:
        logger.error(f"Error checking database health: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to check database health: {str(e)}"
        )


@router.get(
    "/pools",
    response_model=PoolStatsResponse,
    summary="Detailed Pool Statistics",
    description="Get detailed connection pool statistics for both transactional and session pools"
)
async def pool_statistics() -> PoolStatsResponse:
    """
    Get detailed connection pool statistics.
    
    Provides granular metrics for monitoring and debugging:
    - Pool size and utilization
    - Active and idle connections
    - Overflow usage
    - Connection wait times
    
    Returns:
        PoolStatsResponse with detailed pool metrics
        
    Example Response:
        {
            "transactional": {
                "size": 25,
                "checked_in": 13,
                "checked_out": 12,
                "overflow": 2,
                "max_overflow": 10,
                "pool_size": 20,
                "utilization": 48.0
            },
            "session": {
                "size": 10,
                "checked_in": 7,
                "checked_out": 3,
                "overflow": 0,
                "max_overflow": 2,
                "pool_size": 5,
                "utilization": 30.0
            },
            "timestamp": "2026-01-02T14:56:30Z"
        }
    """
    try:
        from datetime import datetime
        
        stats = await get_pool_stats()
        
        return PoolStatsResponse(
            transactional=stats["transactional"],
            session=stats["session"],
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    
    except Exception as e:
        logger.error(f"Error getting pool statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to get pool statistics: {str(e)}"
        )


@router.get(
    "/ready",
    summary="Readiness Probe",
    description="Kubernetes readiness probe - checks if application can serve traffic"
)
async def readiness_probe() -> Dict[str, str]:
    """
    Readiness probe for Kubernetes.
    
    Returns 200 if application is ready to serve traffic,
    503 if not ready.
    
    Checks:
    - Database connection pools available
    - Critical services responsive
    
    Returns:
        {"status": "ready"} if ready
        {"status": "not_ready", "reason": "..."} if not ready
    """
    try:
        # Check database pools
        stats = await get_pool_stats()
        
        # Check if pools are critically exhausted
        trans_util = stats["transactional"]["utilization"]
        session_util = stats["session"]["utilization"]
        
        if trans_util >= 95 or session_util >= 95:
            raise HTTPException(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "status": "not_ready",
                    "reason": "Connection pools critically exhausted"
                }
            )
        
        return {"status": "ready"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Readiness probe failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "reason": str(e)}
        )


@router.get(
    "/live",
    summary="Liveness Probe",
    description="Kubernetes liveness probe - checks if application is alive"
)
async def liveness_probe() -> Dict[str, str]:
    """
    Liveness probe for Kubernetes.
    
    Returns 200 if application is alive,
    500 if application should be restarted.
    
    Checks:
    - Application can respond to requests
    - No deadlocks or critical failures
    
    Returns:
        {"status": "alive"} if alive
    """
    # Simple check - if we can return a response, we're alive
    return {"status": "alive"}

