"""
Vector Storage Integrity Checker.

Implements Task P0-24: Vector Storage Integrity Validation Pipeline

This module validates embeddings AFTER storage to detect:
1. Dimension mismatches (stored dimension != expected)
2. Data corruption (NaN, Inf values after storage)
3. Metadata inconsistency (tenant_id, user_id mismatch)
4. Orphaned embeddings (source_metric_id invalid)
5. Duplicate embeddings (same content, different IDs)

CRITICAL: Prevents silent data corruption causing production crashes.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import UUID
from dataclasses import dataclass, field
import numpy as np

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class IntegrityViolation:
    """Represents a detected integrity violation."""
    
    embedding_id: str
    violation_type: str  # dimension_mismatch, data_corruption, metadata_inconsistency, orphaned, duplicate
    severity: str  # critical, high, medium, low
    description: str
    detected_at: datetime = field(default_factory=datetime.utcnow)
    auto_fixable: bool = False
    fix_action: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class VectorIntegrityChecker:
    """
    Post-storage integrity validator for pgvector embeddings.
    
    Validates embeddings AFTER database storage to ensure:
    - No data corruption occurred
    - Dimensions match expected values
    - Metadata is consistent
    - Relationships are valid
    
    Usage:
        checker = VectorIntegrityChecker(session)
        
        # Validate single embedding
        violations = await checker.validate_embedding(embedding_id)
        
        # Validate all embeddings for tenant
        violations = await checker.validate_tenant_embeddings(tenant_id)
        
        # Run full integrity scan
        report = await checker.run_integrity_scan()
    """
    
    EXPECTED_DIMENSION = 1536  # text-embedding-3-small
    MIN_MAGNITUDE = 0.01
    MAX_MAGNITUDE = 10.0
    
    def __init__(self, session: AsyncSession):
        """
        Initialize integrity checker.
        
        Args:
            session: Async database session
        """
        self.session = session
        self.violations: List[IntegrityViolation] = []
    
    async def validate_embedding(
        self,
        embedding_id: UUID,
        expected_dimension: int = EXPECTED_DIMENSION
    ) -> List[IntegrityViolation]:
        """
        Validate single embedding integrity.
        
        Performs 5 critical checks:
        1. Dimension validation
        2. Data corruption detection (NaN/Inf)
        3. Zero vector detection
        4. Magnitude validation
        5. Metadata consistency
        
        Args:
            embedding_id: Embedding UUID
            expected_dimension: Expected vector dimension
        
        Returns:
            List of detected violations
        """
        violations = []
        
        try:
            # Fetch embedding from database
            result = await self.session.execute(
                text("""
                    SELECT 
                        id,
                        tenant_id,
                        user_id,
                        content,
                        embedding,
                        embedding_dimensions,
                        embedding_model,
                        quality_score,
                        validation_errors,
                        source_metric_id,
                        created_at
                    FROM ga4_embeddings
                    WHERE id = :embedding_id
                """),
                {"embedding_id": embedding_id}
            )
            
            row = result.fetchone()
            
            if not row:
                violations.append(IntegrityViolation(
                    embedding_id=str(embedding_id),
                    violation_type="not_found",
                    severity="critical",
                    description=f"Embedding {embedding_id} not found in database",
                    auto_fixable=False
                ))
                return violations
            
            # Extract values
            stored_id, tenant_id, user_id, content, embedding, embedding_dims, \
                embedding_model, quality_score, validation_errors, source_metric_id, created_at = row
            
            # Check 1: Dimension validation
            if embedding_dims != expected_dimension:
                violations.append(IntegrityViolation(
                    embedding_id=str(embedding_id),
                    violation_type="dimension_mismatch",
                    severity="critical",
                    description=f"Dimension mismatch: stored={embedding_dims}, expected={expected_dimension}",
                    auto_fixable=False,
                    metadata={
                        "stored_dimension": embedding_dims,
                        "expected_dimension": expected_dimension
                    }
                ))
            
            # Check 2: Actual vector dimension (redundant check)
            if isinstance(embedding, (list, np.ndarray)):
                actual_dim = len(embedding)
                if actual_dim != expected_dimension:
                    violations.append(IntegrityViolation(
                        embedding_id=str(embedding_id),
                        violation_type="vector_dimension_mismatch",
                        severity="critical",
                        description=f"Vector dimension mismatch: actual={actual_dim}, expected={expected_dimension}",
                        auto_fixable=False,
                        metadata={
                            "actual_dimension": actual_dim,
                            "expected_dimension": expected_dimension,
                            "stored_dimension": embedding_dims
                        }
                    ))
            
            # Check 3: Data corruption (NaN/Inf)
            if isinstance(embedding, (list, np.ndarray)):
                vec = np.array(embedding, dtype=np.float32)
                
                if np.isnan(vec).any():
                    nan_count = np.isnan(vec).sum()
                    violations.append(IntegrityViolation(
                        embedding_id=str(embedding_id),
                        violation_type="data_corruption",
                        severity="critical",
                        description=f"Vector contains {nan_count} NaN values",
                        auto_fixable=True,
                        fix_action="delete_and_regenerate",
                        metadata={"nan_count": int(nan_count)}
                    ))
                
                if np.isinf(vec).any():
                    inf_count = np.isinf(vec).sum()
                    violations.append(IntegrityViolation(
                        embedding_id=str(embedding_id),
                        violation_type="data_corruption",
                        severity="critical",
                        description=f"Vector contains {inf_count} Inf values",
                        auto_fixable=True,
                        fix_action="delete_and_regenerate",
                        metadata={"inf_count": int(inf_count)}
                    ))
                
                # Check 4: Zero vector
                if np.all(vec == 0):
                    violations.append(IntegrityViolation(
                        embedding_id=str(embedding_id),
                        violation_type="zero_vector",
                        severity="high",
                        description="Vector is all zeros",
                        auto_fixable=True,
                        fix_action="regenerate",
                        metadata={"zero_elements": int(expected_dimension)}
                    ))
                
                # Check 5: Magnitude validation
                magnitude = np.linalg.norm(vec)
                if magnitude < self.MIN_MAGNITUDE:
                    violations.append(IntegrityViolation(
                        embedding_id=str(embedding_id),
                        violation_type="magnitude_too_low",
                        severity="medium",
                        description=f"Vector magnitude too low: {magnitude:.6f} < {self.MIN_MAGNITUDE}",
                        auto_fixable=True,
                        fix_action="regenerate",
                        metadata={"magnitude": float(magnitude)}
                    ))
                
                if magnitude > self.MAX_MAGNITUDE:
                    violations.append(IntegrityViolation(
                        embedding_id=str(embedding_id),
                        violation_type="magnitude_too_high",
                        severity="medium",
                        description=f"Vector magnitude too high: {magnitude:.6f} > {self.MAX_MAGNITUDE}",
                        auto_fixable=True,
                        fix_action="normalize",
                        metadata={"magnitude": float(magnitude)}
                    ))
            
            # Check 6: Metadata consistency
            if not tenant_id:
                violations.append(IntegrityViolation(
                    embedding_id=str(embedding_id),
                    violation_type="metadata_inconsistency",
                    severity="critical",
                    description="Missing tenant_id",
                    auto_fixable=False
                ))
            
            if not user_id:
                violations.append(IntegrityViolation(
                    embedding_id=str(embedding_id),
                    violation_type="metadata_inconsistency",
                    severity="high",
                    description="Missing user_id",
                    auto_fixable=False
                ))
            
            # Check 7: Content validation
            if not content or len(content.strip()) == 0:
                violations.append(IntegrityViolation(
                    embedding_id=str(embedding_id),
                    violation_type="empty_content",
                    severity="high",
                    description="Empty or whitespace-only content",
                    auto_fixable=False,
                    metadata={"content_length": len(content) if content else 0}
                ))
            
            # Check 8: Quality score validation
            if quality_score is not None and (quality_score < 0 or quality_score > 1):
                violations.append(IntegrityViolation(
                    embedding_id=str(embedding_id),
                    violation_type="invalid_quality_score",
                    severity="low",
                    description=f"Quality score out of range: {quality_score}",
                    auto_fixable=True,
                    fix_action="recalculate_quality",
                    metadata={"quality_score": quality_score}
                ))
        
        except Exception as e:
            logger.error(f"Error validating embedding {embedding_id}: {e}", exc_info=True)
            violations.append(IntegrityViolation(
                embedding_id=str(embedding_id),
                violation_type="validation_error",
                severity="critical",
                description=f"Validation failed: {str(e)}",
                auto_fixable=False
            ))
        
        # Store violations
        self.violations.extend(violations)
        
        return violations
    
    async def validate_tenant_embeddings(
        self,
        tenant_id: UUID,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Validate all embeddings for a tenant.
        
        Args:
            tenant_id: Tenant UUID
            limit: Maximum embeddings to validate (None = all)
        
        Returns:
            Validation report
        """
        logger.info(f"Starting integrity validation for tenant {tenant_id}")
        
        # Get all embedding IDs for tenant
        query = """
            SELECT id FROM ga4_embeddings
            WHERE tenant_id = :tenant_id
            ORDER BY created_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"
        
        result = await self.session.execute(
            text(query),
            {"tenant_id": tenant_id}
        )
        
        embedding_ids = [row[0] for row in result.fetchall()]
        
        logger.info(f"Found {len(embedding_ids)} embeddings for tenant {tenant_id}")
        
        # Validate each embedding
        all_violations = []
        for embedding_id in embedding_ids:
            violations = await self.validate_embedding(embedding_id)
            all_violations.extend(violations)
        
        # Generate report
        report = self._generate_report(all_violations, len(embedding_ids))
        report["tenant_id"] = str(tenant_id)
        
        return report
    
    async def run_integrity_scan(
        self,
        max_embeddings: int = 10000
    ) -> Dict[str, Any]:
        """
        Run full database integrity scan.
        
        Validates up to max_embeddings across all tenants.
        
        Args:
            max_embeddings: Maximum embeddings to scan
        
        Returns:
            Comprehensive integrity report
        """
        logger.info(f"Starting full integrity scan (max: {max_embeddings} embeddings)")
        
        # Get all embedding IDs
        result = await self.session.execute(
            text(f"""
                SELECT id FROM ga4_embeddings
                ORDER BY created_at DESC
                LIMIT {max_embeddings}
            """)
        )
        
        embedding_ids = [row[0] for row in result.fetchall()]
        
        logger.info(f"Scanning {len(embedding_ids)} embeddings")
        
        # Validate each
        all_violations = []
        for i, embedding_id in enumerate(embedding_ids):
            if i > 0 and i % 1000 == 0:
                logger.info(f"Scanned {i}/{len(embedding_ids)} embeddings")
            
            violations = await self.validate_embedding(embedding_id)
            all_violations.extend(violations)
        
        # Generate comprehensive report
        report = self._generate_report(all_violations, len(embedding_ids))
        report["scan_type"] = "full"
        report["max_embeddings"] = max_embeddings
        
        logger.info(f"Integrity scan complete: {len(all_violations)} violations found")
        
        return report
    
    def _generate_report(
        self,
        violations: List[IntegrityViolation],
        total_embeddings: int
    ) -> Dict[str, Any]:
        """Generate integrity report from violations."""
        if total_embeddings == 0:
            return {
                "total_embeddings": 0,
                "violations_found": 0,
                "integrity_score": 100.0,
                "violations_by_type": {},
                "violations_by_severity": {},
                "auto_fixable_count": 0,
                "generated_at": datetime.utcnow().isoformat()
            }
        
        # Group by type
        by_type = {}
        for v in violations:
            by_type[v.violation_type] = by_type.get(v.violation_type, 0) + 1
        
        # Group by severity
        by_severity = {}
        for v in violations:
            by_severity[v.severity] = by_severity.get(v.severity, 0) + 1
        
        # Count auto-fixable
        auto_fixable = sum(1 for v in violations if v.auto_fixable)
        
        # Calculate integrity score
        critical_count = by_severity.get("critical", 0)
        high_count = by_severity.get("high", 0)
        medium_count = by_severity.get("medium", 0)
        
        # Weighted penalty
        penalty = (
            critical_count * 10 +
            high_count * 5 +
            medium_count * 2
        )
        
        integrity_score = max(0, 100 - (penalty / total_embeddings * 100))
        
        return {
            "total_embeddings": total_embeddings,
            "violations_found": len(violations),
            "integrity_score": round(integrity_score, 2),
            "violations_by_type": by_type,
            "violations_by_severity": by_severity,
            "auto_fixable_count": auto_fixable,
            "critical_violations": [
                {
                    "embedding_id": v.embedding_id,
                    "type": v.violation_type,
                    "description": v.description
                }
                for v in violations if v.severity == "critical"
            ][:10],  # Show first 10 critical
            "generated_at": datetime.utcnow().isoformat()
        }
    
    async def check_orphaned_embeddings(self) -> List[IntegrityViolation]:
        """
        Check for orphaned embeddings (invalid source_metric_id).
        
        Returns:
            List of orphaned embedding violations
        """
        logger.info("Checking for orphaned embeddings")
        
        # Find embeddings with source_metric_id that don't exist in ga4_metrics_raw
        result = await self.session.execute(
            text("""
                SELECT e.id, e.source_metric_id
                FROM ga4_embeddings e
                WHERE e.source_metric_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM ga4_metrics_raw m
                      WHERE m.id = e.source_metric_id
                  )
                LIMIT 1000
            """)
        )
        
        violations = []
        for row in result.fetchall():
            embedding_id, source_metric_id = row
            violations.append(IntegrityViolation(
                embedding_id=str(embedding_id),
                violation_type="orphaned",
                severity="medium",
                description=f"Source metric {source_metric_id} does not exist",
                auto_fixable=True,
                fix_action="set_source_metric_id_null",
                metadata={"source_metric_id": source_metric_id}
            ))
        
        logger.info(f"Found {len(violations)} orphaned embeddings")
        
        self.violations.extend(violations)
        return violations
    
    async def check_duplicate_embeddings(
        self,
        tenant_id: Optional[UUID] = None
    ) -> List[IntegrityViolation]:
        """
        Check for duplicate embeddings (same content, different IDs).
        
        Args:
            tenant_id: Optional tenant to scope check
        
        Returns:
            List of duplicate violations
        """
        logger.info("Checking for duplicate embeddings")
        
        where_clause = ""
        params = {}
        if tenant_id:
            where_clause = "WHERE tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id
        
        # Find duplicate content
        result = await self.session.execute(
            text(f"""
                SELECT content, COUNT(*), array_agg(id::text)
                FROM ga4_embeddings
                {where_clause}
                GROUP BY content
                HAVING COUNT(*) > 1
                LIMIT 100
            """),
            params
        )
        
        violations = []
        for row in result.fetchall():
            content, count, ids = row
            # Mark all but first as duplicates
            for duplicate_id in ids[1:]:
                violations.append(IntegrityViolation(
                    embedding_id=duplicate_id,
                    violation_type="duplicate",
                    severity="low",
                    description=f"Duplicate content (original: {ids[0]})",
                    auto_fixable=True,
                    fix_action="delete",
                    metadata={
                        "original_id": ids[0],
                        "duplicate_count": count - 1
                    }
                ))
        
        logger.info(f"Found {len(violations)} duplicate embeddings")
        
        self.violations.extend(violations)
        return violations

