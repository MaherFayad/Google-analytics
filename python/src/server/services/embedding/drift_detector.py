"""
Semantic Drift Detection for Embedding Models.

Implements Task P0-5: Embedding Quality Assurance Pipeline

Features:
- Monthly drift detection
- Baseline comparison
- Alert triggering for significant drift
- Historical tracking

Detects when embedding model behavior changes significantly,
which could indicate:
- Model updates from OpenAI
- Configuration changes
- Data quality degradation
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DriftDetectionResult(BaseModel):
    """Result of drift detection analysis."""
    
    drift_detected: bool
    avg_similarity_to_baseline: float = Field(
        ge=0.0, le=1.0,
        description="Average similarity to baseline embeddings"
    )
    drift_threshold: float = 0.95
    sample_size: int
    baseline_date: datetime
    current_date: datetime
    alert_level: str = Field(
        description="none, warning, critical"
    )
    details: Dict[str, Any] = Field(default_factory=dict)


class SemanticDriftDetector:
    """
    Detect semantic drift in embedding models.
    
    Implements Task P0-5: Drift detection component
    
    Monitors embedding quality over time by:
    1. Maintaining baseline embeddings for reference texts
    2. Periodically re-embedding reference texts
    3. Computing similarity to baseline
    4. Alert if similarity drops below threshold (95%)
    
    Usage:
        detector = SemanticDriftDetector(redis_client)
        
        # Run monthly drift detection
        result = await detector.detect_drift(tenant_id="tenant-123")
        
        if result.drift_detected:
            # Alert admin team
            await send_alert(result)
    """
    
    DRIFT_THRESHOLD = 0.95  # 95% similarity required
    BASELINE_KEY_PREFIX = "embedding:baseline:"
    DRIFT_HISTORY_KEY = "embedding:drift_history:"
    
    # Reference texts for drift detection
    REFERENCE_TEXTS = [
        "Mobile conversions increased significantly last week",
        "Desktop traffic showed steady growth over the past month",
        "Bounce rate decreased by 15% on landing pages",
        "Average session duration improved across all devices",
        "New user acquisition remained stable throughout the quarter"
    ]
    
    def __init__(self, redis_client, embedding_generator):
        """
        Initialize drift detector.
        
        Args:
            redis_client: Redis client for storing baselines
            embedding_generator: Generator for creating embeddings
        """
        self.redis = redis_client
        self.embedding_generator = embedding_generator
        
        logger.info("Semantic drift detector initialized")
    
    async def initialize_baseline(
        self,
        tenant_id: str,
        force_refresh: bool = False
    ):
        """
        Initialize baseline embeddings for reference texts.
        
        Args:
            tenant_id: Tenant ID
            force_refresh: Force refresh even if baseline exists
        """
        baseline_key = f"{self.BASELINE_KEY_PREFIX}{tenant_id}"
        
        # Check if baseline exists
        if not force_refresh:
            existing = await self.redis.get(baseline_key)
            if existing:
                logger.info(f"Baseline already exists for tenant {tenant_id}")
                return
        
        logger.info(f"Initializing baseline embeddings for tenant {tenant_id}")
        
        # Generate embeddings for reference texts
        baselines = []
        for text in self.REFERENCE_TEXTS:
            embedding = await self.embedding_generator.generate(text)
            baselines.append({
                "text": text,
                "embedding": embedding,
                "generated_at": datetime.utcnow().isoformat()
            })
        
        # Store in Redis (no expiration for baseline)
        import json
        await self.redis.set(baseline_key, json.dumps(baselines))
        
        logger.info(
            f"Baseline initialized with {len(baselines)} reference embeddings"
        )
    
    async def detect_drift(
        self,
        tenant_id: str
    ) -> DriftDetectionResult:
        """
        Detect semantic drift by comparing to baseline.
        
        Args:
            tenant_id: Tenant ID
        
        Returns:
            DriftDetectionResult with drift analysis
        """
        logger.info(f"Running drift detection for tenant {tenant_id}")
        
        # Get baseline
        baseline_key = f"{self.BASELINE_KEY_PREFIX}{tenant_id}"
        baseline_data = await self.redis.get(baseline_key)
        
        if not baseline_data:
            logger.warning(f"No baseline found for tenant {tenant_id}, initializing...")
            await self.initialize_baseline(tenant_id)
            
            # Return no drift (just initialized)
            return DriftDetectionResult(
                drift_detected=False,
                avg_similarity_to_baseline=1.0,
                sample_size=0,
                baseline_date=datetime.utcnow(),
                current_date=datetime.utcnow(),
                alert_level="none",
                details={"status": "baseline_initialized"}
            )
        
        # Parse baseline
        import json
        baselines = json.loads(baseline_data)
        baseline_date = datetime.fromisoformat(baselines[0]["generated_at"])
        
        # Re-embed reference texts
        similarities = []
        for baseline in baselines:
            text = baseline["text"]
            baseline_embedding = baseline["embedding"]
            
            # Generate new embedding
            new_embedding = await self.embedding_generator.generate(text)
            
            # Compute similarity
            similarity = self._cosine_similarity(baseline_embedding, new_embedding)
            similarities.append(similarity)
            
            logger.debug(
                f"Drift check: '{text[:40]}...' similarity={similarity:.4f}"
            )
        
        # Calculate average similarity
        avg_similarity = float(np.mean(similarities))
        min_similarity = float(np.min(similarities))
        
        # Determine drift
        drift_detected = avg_similarity < self.DRIFT_THRESHOLD
        
        # Determine alert level
        if avg_similarity >= 0.95:
            alert_level = "none"
        elif avg_similarity >= 0.90:
            alert_level = "warning"
        else:
            alert_level = "critical"
        
        result = DriftDetectionResult(
            drift_detected=drift_detected,
            avg_similarity_to_baseline=avg_similarity,
            drift_threshold=self.DRIFT_THRESHOLD,
            sample_size=len(similarities),
            baseline_date=baseline_date,
            current_date=datetime.utcnow(),
            alert_level=alert_level,
            details={
                "min_similarity": min_similarity,
                "max_similarity": float(np.max(similarities)),
                "similarities": [round(s, 4) for s in similarities]
            }
        )
        
        # Store drift history
        await self._record_drift_history(tenant_id, result)
        
        # Log result
        if drift_detected:
            logger.warning(
                f"DRIFT DETECTED for tenant {tenant_id}: "
                f"avg_similarity={avg_similarity:.4f} "
                f"(threshold={self.DRIFT_THRESHOLD})"
            )
        else:
            logger.info(
                f"No drift detected for tenant {tenant_id}: "
                f"avg_similarity={avg_similarity:.4f}"
            )
        
        return result
    
    async def _record_drift_history(
        self,
        tenant_id: str,
        result: DriftDetectionResult
    ):
        """Record drift detection result in history."""
        history_key = f"{self.DRIFT_HISTORY_KEY}{tenant_id}"
        
        # Store as sorted set (score = timestamp)
        score = result.current_date.timestamp()
        import json
        await self.redis.zadd(
            history_key,
            {json.dumps(result.dict()): score}
        )
        
        # Keep only last 12 months of history
        one_year_ago = (datetime.utcnow() - timedelta(days=365)).timestamp()
        await self.redis.zremrangebyscore(history_key, '-inf', one_year_ago)
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity."""
        arr1 = np.array(vec1)
        arr2 = np.array(vec2)
        
        dot_product = np.dot(arr1, arr2)
        norm1 = np.linalg.norm(arr1)
        norm2 = np.linalg.norm(arr2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(max(0.0, min(1.0, dot_product / (norm1 * norm2))))

