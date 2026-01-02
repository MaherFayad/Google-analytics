"""
Vector Storage Repair Job.

Implements Task P0-24: Automatic repair of vector storage violations

This module repairs common integrity violations:
1. Delete corrupted embeddings (NaN/Inf)
2. Normalize high-magnitude vectors
3. Remove duplicate embeddings
4. Clear invalid source_metric_id references
5. Recalculate quality scores

CRITICAL: Always backup before running repairs.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import UUID
import numpy as np

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .integrity_checker import IntegrityViolation, VectorIntegrityChecker

logger = logging.getLogger(__name__)


class RepairError(Exception):
    """Raised when repair operation fails."""
    pass


class VectorRepairJob:
    """
    Automatic repair service for vector storage violations.
    
    Repairs common issues detected by VectorIntegrityChecker:
    - Corrupted embeddings (NaN/Inf) → Delete
    - High magnitude vectors → Normalize
    - Duplicate embeddings → Delete duplicates
    - Orphaned embeddings → Clear source_metric_id
    - Invalid quality scores → Recalculate
    
    Usage:
        repair_job = VectorRepairJob(session)
        
        # Repair specific violations
        results = await repair_job.repair_violations(violations)
        
        # Run automatic repair for tenant
        report = await repair_job.repair_tenant(tenant_id, dry_run=True)
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize repair job.
        
        Args:
            session: Async database session
        """
        self.session = session
        self.repaired_count = 0
        self.failed_count = 0
    
    async def repair_violations(
        self,
        violations: List[IntegrityViolation],
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Repair list of violations.
        
        Args:
            violations: List of violations to repair
            dry_run: If True, only simulate repairs
        
        Returns:
            Repair report
        """
        logger.info(
            f"Starting repair job: {len(violations)} violations "
            f"(dry_run={dry_run})"
        )
        
        repaired = []
        failed = []
        skipped = []
        
        for violation in violations:
            try:
                if not violation.auto_fixable:
                    skipped.append({
                        "embedding_id": violation.embedding_id,
                        "reason": "not_auto_fixable",
                        "type": violation.violation_type
                    })
                    continue
                
                if dry_run:
                    # Simulate repair
                    repaired.append({
                        "embedding_id": violation.embedding_id,
                        "type": violation.violation_type,
                        "action": violation.fix_action,
                        "simulated": True
                    })
                else:
                    # Execute repair
                    result = await self._execute_repair(violation)
                    repaired.append(result)
                    self.repaired_count += 1
            
            except Exception as e:
                logger.error(
                    f"Failed to repair {violation.embedding_id}: {e}",
                    exc_info=True
                )
                failed.append({
                    "embedding_id": violation.embedding_id,
                    "error": str(e),
                    "type": violation.violation_type
                })
                self.failed_count += 1
        
        return {
            "dry_run": dry_run,
            "total_violations": len(violations),
            "repaired_count": len(repaired),
            "failed_count": len(failed),
            "skipped_count": len(skipped),
            "repaired": repaired,
            "failed": failed,
            "skipped": skipped,
            "completed_at": datetime.utcnow().isoformat()
        }
    
    async def _execute_repair(
        self,
        violation: IntegrityViolation
    ) -> Dict[str, Any]:
        """
        Execute repair for single violation.
        
        Args:
            violation: Violation to repair
        
        Returns:
            Repair result
        """
        action = violation.fix_action
        embedding_id = violation.embedding_id
        
        if action == "delete_and_regenerate":
            # Delete corrupted embedding
            await self._delete_embedding(embedding_id)
            return {
                "embedding_id": embedding_id,
                "type": violation.violation_type,
                "action": "deleted",
                "description": "Corrupted embedding deleted (needs regeneration)"
            }
        
        elif action == "normalize":
            # Normalize high-magnitude vector
            await self._normalize_embedding(embedding_id)
            return {
                "embedding_id": embedding_id,
                "type": violation.violation_type,
                "action": "normalized",
                "description": "Vector normalized to unit length"
            }
        
        elif action == "delete":
            # Delete duplicate
            await self._delete_embedding(embedding_id)
            return {
                "embedding_id": embedding_id,
                "type": violation.violation_type,
                "action": "deleted",
                "description": "Duplicate embedding deleted"
            }
        
        elif action == "set_source_metric_id_null":
            # Clear invalid source_metric_id
            await self._clear_source_metric_id(embedding_id)
            return {
                "embedding_id": embedding_id,
                "type": violation.violation_type,
                "action": "source_metric_id_cleared",
                "description": "Invalid source_metric_id set to NULL"
            }
        
        elif action == "recalculate_quality":
            # Recalculate quality score
            new_score = await self._recalculate_quality(embedding_id)
            return {
                "embedding_id": embedding_id,
                "type": violation.violation_type,
                "action": "quality_recalculated",
                "description": f"Quality score recalculated: {new_score:.4f}"
            }
        
        elif action == "regenerate":
            # Delete and mark for regeneration
            await self._mark_for_regeneration(embedding_id)
            return {
                "embedding_id": embedding_id,
                "type": violation.violation_type,
                "action": "marked_for_regeneration",
                "description": "Embedding marked for regeneration"
            }
        
        else:
            raise RepairError(f"Unknown repair action: {action}")
    
    async def _delete_embedding(self, embedding_id: str):
        """Delete embedding from database."""
        await self.session.execute(
            text("DELETE FROM ga4_embeddings WHERE id = :id"),
            {"id": UUID(embedding_id)}
        )
        await self.session.commit()
        logger.info(f"Deleted embedding {embedding_id}")
    
    async def _normalize_embedding(self, embedding_id: str):
        """Normalize embedding to unit length."""
        # Get current embedding
        result = await self.session.execute(
            text("SELECT embedding FROM ga4_embeddings WHERE id = :id"),
            {"id": UUID(embedding_id)}
        )
        row = result.fetchone()
        if not row:
            raise RepairError(f"Embedding {embedding_id} not found")
        
        embedding = np.array(row[0], dtype=np.float32)
        
        # Normalize
        magnitude = np.linalg.norm(embedding)
        if magnitude > 0:
            normalized = (embedding / magnitude).tolist()
            
            # Update in database
            await self.session.execute(
                text("UPDATE ga4_embeddings SET embedding = :embedding WHERE id = :id"),
                {"embedding": normalized, "id": UUID(embedding_id)}
            )
            await self.session.commit()
            logger.info(f"Normalized embedding {embedding_id}")
        else:
            raise RepairError(f"Cannot normalize zero vector: {embedding_id}")
    
    async def _clear_source_metric_id(self, embedding_id: str):
        """Clear invalid source_metric_id."""
        await self.session.execute(
            text("UPDATE ga4_embeddings SET source_metric_id = NULL WHERE id = :id"),
            {"id": UUID(embedding_id)}
        )
        await self.session.commit()
        logger.info(f"Cleared source_metric_id for {embedding_id}")
    
    async def _recalculate_quality(self, embedding_id: str) -> float:
        """Recalculate quality score."""
        # Get embedding
        result = await self.session.execute(
            text("SELECT embedding FROM ga4_embeddings WHERE id = :id"),
            {"id": UUID(embedding_id)}
        )
        row = result.fetchone()
        if not row:
            raise RepairError(f"Embedding {embedding_id} not found")
        
        embedding = np.array(row[0], dtype=np.float32)
        
        # Calculate quality metrics
        magnitude = np.linalg.norm(embedding)
        zero_count = np.sum(embedding == 0)
        zero_ratio = zero_count / len(embedding)
        
        # Simple quality score: 1.0 - penalties
        quality = 1.0
        
        # Penalty for low magnitude
        if magnitude < 0.5:
            quality -= 0.3
        
        # Penalty for many zeros
        if zero_ratio > 0.1:
            quality -= zero_ratio
        
        quality = max(0.0, min(1.0, quality))
        
        # Update in database
        await self.session.execute(
            text("UPDATE ga4_embeddings SET quality_score = :score WHERE id = :id"),
            {"score": quality, "id": UUID(embedding_id)}
        )
        await self.session.commit()
        
        logger.info(f"Recalculated quality for {embedding_id}: {quality:.4f}")
        return quality
    
    async def _mark_for_regeneration(self, embedding_id: str):
        """Mark embedding for regeneration (add to errors list)."""
        await self.session.execute(
            text("""
                UPDATE ga4_embeddings 
                SET validation_errors = 
                    COALESCE(validation_errors, '[]'::jsonb) || 
                    '["marked_for_regeneration"]'::jsonb
                WHERE id = :id
            """),
            {"id": UUID(embedding_id)}
        )
        await self.session.commit()
        logger.info(f"Marked {embedding_id} for regeneration")
    
    async def repair_tenant(
        self,
        tenant_id: UUID,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Run automatic repair for tenant.
        
        Steps:
        1. Run integrity check
        2. Filter auto-fixable violations
        3. Execute repairs
        4. Run integrity check again
        5. Generate report
        
        Args:
            tenant_id: Tenant UUID
            dry_run: If True, only simulate repairs
        
        Returns:
            Comprehensive repair report
        """
        logger.info(f"Starting repair job for tenant {tenant_id} (dry_run={dry_run})")
        
        # Step 1: Initial integrity check
        checker = VectorIntegrityChecker(self.session)
        initial_report = await checker.validate_tenant_embeddings(tenant_id)
        
        # Step 2: Get auto-fixable violations
        auto_fixable = [v for v in checker.violations if v.auto_fixable]
        
        logger.info(
            f"Found {len(checker.violations)} violations, "
            f"{len(auto_fixable)} auto-fixable"
        )
        
        # Step 3: Execute repairs
        repair_results = await self.repair_violations(auto_fixable, dry_run=dry_run)
        
        # Step 4: Re-check (only if not dry run)
        final_report = None
        if not dry_run:
            checker_after = VectorIntegrityChecker(self.session)
            final_report = await checker_after.validate_tenant_embeddings(tenant_id)
        
        # Step 5: Generate comprehensive report
        return {
            "tenant_id": str(tenant_id),
            "dry_run": dry_run,
            "initial_integrity_score": initial_report["integrity_score"],
            "final_integrity_score": final_report["integrity_score"] if final_report else None,
            "improvement": (
                final_report["integrity_score"] - initial_report["integrity_score"]
                if final_report else 0
            ),
            "repair_results": repair_results,
            "completed_at": datetime.utcnow().isoformat()
        }
    
    async def get_repair_statistics(self) -> Dict[str, Any]:
        """Get repair job statistics."""
        return {
            "repaired_count": self.repaired_count,
            "failed_count": self.failed_count,
            "success_rate": (
                self.repaired_count / (self.repaired_count + self.failed_count) * 100
                if (self.repaired_count + self.failed_count) > 0
                else 100.0
            )
        }

