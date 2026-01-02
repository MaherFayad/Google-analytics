"""
Embedding Model Version Migration Coordinator.

Implements Task P0-26: Embedding Model Version Migration Pipeline

Features:
1. Blue-green deployment for embedding model upgrades
2. Zero-downtime migration
3. A/B testing with quality comparison
4. Gradual rollout with rollback capability
5. Per-tenant migration tracking

Migration Strategy:
Phase 1: Generate embeddings with both models (v1 + v2)
Phase 2: A/B test quality on sample data
Phase 3: Gradual traffic shift (10% -> 50% -> 100%)
Phase 4: Deprecate old version after validation period
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from uuid import UUID
from enum import Enum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from .generator import EmbeddingGenerator
from .quality_comparator import EmbeddingQualityComparator
from ..core.config import settings

logger = logging.getLogger(__name__)


class MigrationPhase(str, Enum):
    """Migration phases for gradual rollout."""
    TESTING = "testing"          # A/B testing phase
    ROLLOUT_10 = "rollout_10"    # 10% of traffic
    ROLLOUT_50 = "rollout_50"    # 50% of traffic
    ROLLOUT_100 = "rollout_100"  # 100% of traffic (complete)
    DEPRECATING = "deprecating"  # Old version being phased out
    COMPLETED = "completed"      # Migration complete


class MigrationStatus(str, Enum):
    """Migration status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class EmbeddingModelConfig(BaseModel):
    """Configuration for an embedding model."""
    
    version_name: str = Field(..., description="Version identifier (e.g., v2.0)")
    model_name: str = Field(..., description="OpenAI model name")
    dimensions: int = Field(..., description="Embedding dimensions")
    description: str = Field(default="", description="Human-readable description")
    
    class Config:
        frozen = True


class MigrationResult(BaseModel):
    """Result of migration operation."""
    
    tenant_id: UUID
    source_version: str
    target_version: str
    total_embeddings: int
    migrated_count: int
    failed_count: int
    quality_improvement: Optional[float] = None
    retrieval_improvement: Optional[float] = None
    duration_seconds: float
    status: MigrationStatus


class EmbeddingVersionMigrator:
    """
    Coordinates embedding model version migrations.
    
    Implements blue-green deployment strategy for zero-downtime upgrades.
    
    Example Usage:
        migrator = EmbeddingVersionMigrator(session)
        
        # Define new model version
        new_version = EmbeddingModelConfig(
            version_name="v2.0",
            model_name="text-embedding-3-large",
            dimensions=3072,
            description="Upgraded to larger model for better quality"
        )
        
        # Start migration with A/B testing
        result = await migrator.migrate_tenant(
            tenant_id=UUID("..."),
            target_config=new_version,
            phase=MigrationPhase.TESTING,
            sample_size=100
        )
    """
    
    # Default model configurations
    MODEL_V1 = EmbeddingModelConfig(
        version_name="v1.0",
        model_name="text-embedding-3-small",
        dimensions=1536,
        description="Initial production model"
    )
    
    MODEL_V2 = EmbeddingModelConfig(
        version_name="v2.0",
        model_name="text-embedding-3-large",
        dimensions=3072,
        description="Upgraded large model"
    )
    
    def __init__(self, session: AsyncSession):
        """
        Initialize version migrator.
        
        Args:
            session: Database session
        """
        self.session = session
        self.comparator = EmbeddingQualityComparator(session)
        
        logger.info("Embedding version migrator initialized")
    
    async def register_model_version(
        self,
        config: EmbeddingModelConfig,
        status: str = "testing"
    ) -> int:
        """
        Register a new embedding model version.
        
        Args:
            config: Model configuration
            status: Initial status (testing/active/deprecated/retired)
        
        Returns:
            Version ID
        """
        stmt = text("""
            INSERT INTO embedding_model_versions (
                version_name,
                model_name,
                dimensions,
                status,
                metadata
            ) VALUES (
                :version_name,
                :model_name,
                :dimensions,
                :status,
                :metadata::jsonb
            )
            ON CONFLICT (version_name) DO UPDATE
            SET 
                model_name = EXCLUDED.model_name,
                dimensions = EXCLUDED.dimensions,
                status = EXCLUDED.status,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id
        """)
        
        result = await self.session.execute(
            stmt,
            {
                "version_name": config.version_name,
                "model_name": config.model_name,
                "dimensions": config.dimensions,
                "status": status,
                "metadata": f'{{"description": "{config.description}"}}'
            }
        )
        
        row = result.fetchone()
        await self.session.commit()
        
        logger.info(
            f"Registered model version: {config.version_name} "
            f"({config.model_name}, {config.dimensions}D, status={status})"
        )
        
        return row.id
    
    async def migrate_tenant(
        self,
        tenant_id: UUID,
        user_id: UUID,
        target_config: EmbeddingModelConfig,
        phase: MigrationPhase = MigrationPhase.TESTING,
        sample_size: Optional[int] = None,
        quality_threshold: float = 0.95
    ) -> MigrationResult:
        """
        Migrate tenant's embeddings to new model version.
        
        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            target_config: Target model configuration
            phase: Migration phase (testing/rollout/complete)
            sample_size: Number of records to migrate (None = all)
            quality_threshold: Minimum quality score required
        
        Returns:
            MigrationResult with stats
        
        Example:
            result = await migrator.migrate_tenant(
                tenant_id=UUID("..."),
                user_id=UUID("..."),
                target_config=EmbeddingVersionMigrator.MODEL_V2,
                phase=MigrationPhase.TESTING,
                sample_size=100
            )
        """
        start_time = datetime.now()
        
        # Get current version
        current_version = await self._get_tenant_version(tenant_id)
        
        logger.info(
            f"Starting migration: tenant={tenant_id}, "
            f"{current_version} -> {target_config.version_name}, "
            f"phase={phase.value}"
        )
        
        # Create audit record
        audit_id = await self._create_audit_record(
            tenant_id=tenant_id,
            source_version=current_version,
            target_version=target_config.version_name
        )
        
        # Register target version if not exists
        await self.register_model_version(
            config=target_config,
            status="testing" if phase == MigrationPhase.TESTING else "active"
        )
        
        # Set RLS context
        await self.session.execute(
            text("SET LOCAL app.tenant_id = :tenant_id"),
            {"tenant_id": str(tenant_id)}
        )
        await self.session.execute(
            text("SET LOCAL app.user_id = :user_id"),
            {"user_id": str(user_id)}
        )
        
        try:
            # Phase 1: Generate embeddings with new model
            migration_stats = await self._generate_new_embeddings(
                tenant_id=tenant_id,
                user_id=user_id,
                target_config=target_config,
                sample_size=sample_size
            )
            
            # Phase 2: A/B test quality if in testing phase
            quality_improvement = None
            retrieval_improvement = None
            
            if phase == MigrationPhase.TESTING:
                comparison = await self.comparator.compare_versions(
                    tenant_id=tenant_id,
                    version_a=current_version,
                    version_b=target_config.version_name,
                    sample_size=min(sample_size or 100, 100)
                )
                
                quality_improvement = comparison.quality_improvement_percent
                retrieval_improvement = comparison.retrieval_improvement_percent
                
                logger.info(
                    f"A/B test results: quality={quality_improvement:+.2f}%, "
                    f"retrieval={retrieval_improvement:+.2f}%"
                )
                
                # Check if quality threshold met
                if comparison.version_b_quality_score < quality_threshold:
                    raise Exception(
                        f"Quality threshold not met: "
                        f"{comparison.version_b_quality_score:.4f} < {quality_threshold}"
                    )
            
            # Phase 3: Update migration status based on phase
            if phase == MigrationPhase.ROLLOUT_100 or phase == MigrationPhase.COMPLETED:
                # Mark old embeddings as deprecated
                await self._deprecate_old_version(
                    tenant_id=tenant_id,
                    old_version=current_version
                )
            
            # Update audit record
            duration = (datetime.now() - start_time).total_seconds()
            
            await self._update_audit_record(
                audit_id=audit_id,
                status=MigrationStatus.COMPLETED,
                migrated_count=migration_stats["success"],
                failed_count=migration_stats["failed"],
                quality_improvement=quality_improvement,
                retrieval_improvement=retrieval_improvement
            )
            
            result = MigrationResult(
                tenant_id=tenant_id,
                source_version=current_version,
                target_version=target_config.version_name,
                total_embeddings=migration_stats["processed"],
                migrated_count=migration_stats["success"],
                failed_count=migration_stats["failed"],
                quality_improvement=quality_improvement,
                retrieval_improvement=retrieval_improvement,
                duration_seconds=duration,
                status=MigrationStatus.COMPLETED
            )
            
            logger.info(
                f"Migration completed: tenant={tenant_id}, "
                f"migrated={migration_stats['success']}/{migration_stats['processed']}, "
                f"duration={duration:.2f}s"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            
            # Update audit record
            await self._update_audit_record(
                audit_id=audit_id,
                status=MigrationStatus.FAILED
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return MigrationResult(
                tenant_id=tenant_id,
                source_version=current_version,
                target_version=target_config.version_name,
                total_embeddings=0,
                migrated_count=0,
                failed_count=0,
                duration_seconds=duration,
                status=MigrationStatus.FAILED
            )
    
    async def rollback_migration(
        self,
        tenant_id: UUID,
        target_version: str
    ) -> bool:
        """
        Rollback migration by activating old version.
        
        Args:
            tenant_id: Tenant UUID
            target_version: Version to rollback to
        
        Returns:
            True if successful
        """
        logger.warning(
            f"Rolling back migration: tenant={tenant_id}, "
            f"activating version={target_version}"
        )
        
        # Mark target version as active
        stmt = text("""
            UPDATE ga4_embeddings
            SET migration_status = 'active'
            WHERE tenant_id = :tenant_id
            AND model_version = :version
        """)
        
        await self.session.execute(
            stmt,
            {"tenant_id": str(tenant_id), "version": target_version}
        )
        
        await self.session.commit()
        
        logger.info(f"Rollback completed for tenant {tenant_id}")
        
        return True
    
    async def _get_tenant_version(self, tenant_id: UUID) -> str:
        """Get current active version for tenant."""
        stmt = text("""
            SELECT model_version
            FROM ga4_embeddings
            WHERE tenant_id = :tenant_id
            AND migration_status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
        """)
        
        result = await self.session.execute(
            stmt,
            {"tenant_id": str(tenant_id)}
        )
        
        row = result.fetchone()
        
        return row.model_version if row else "v1.0"
    
    async def _generate_new_embeddings(
        self,
        tenant_id: UUID,
        user_id: UUID,
        target_config: EmbeddingModelConfig,
        sample_size: Optional[int]
    ) -> Dict[str, int]:
        """Generate embeddings with new model version."""
        generator = EmbeddingGenerator(self.session)
        
        # Temporarily override generator's model config
        original_model = generator.MODEL
        original_dimensions = generator.DIMENSIONS
        
        generator.MODEL = target_config.model_name
        generator.DIMENSIONS = target_config.dimensions
        
        try:
            stats = await generator.generate_embeddings_for_metrics(
                tenant_id=tenant_id,
                user_id=user_id,
                limit=sample_size
            )
            
            # Update embeddings with version info
            await self._tag_embeddings_with_version(
                tenant_id=tenant_id,
                version=target_config.version_name,
                model_name=target_config.model_name
            )
            
            return stats
        
        finally:
            # Restore original config
            generator.MODEL = original_model
            generator.DIMENSIONS = original_dimensions
    
    async def _tag_embeddings_with_version(
        self,
        tenant_id: UUID,
        version: str,
        model_name: str
    ):
        """Tag recently created embeddings with version."""
        stmt = text("""
            UPDATE ga4_embeddings
            SET 
                model_version = :version,
                migration_status = 'active'
            WHERE tenant_id = :tenant_id
            AND embedding_model = :model_name
            AND model_version IS NULL
            AND created_at > NOW() - INTERVAL '1 hour'
        """)
        
        await self.session.execute(
            stmt,
            {
                "tenant_id": str(tenant_id),
                "version": version,
                "model_name": model_name
            }
        )
        
        await self.session.commit()
    
    async def _deprecate_old_version(
        self,
        tenant_id: UUID,
        old_version: str
    ):
        """Mark old version embeddings as deprecated."""
        stmt = text("""
            UPDATE ga4_embeddings
            SET migration_status = 'deprecated'
            WHERE tenant_id = :tenant_id
            AND model_version = :version
            AND migration_status = 'active'
        """)
        
        await self.session.execute(
            stmt,
            {"tenant_id": str(tenant_id), "version": old_version}
        )
        
        await self.session.commit()
    
    async def _create_audit_record(
        self,
        tenant_id: UUID,
        source_version: str,
        target_version: str
    ) -> int:
        """Create migration audit record."""
        stmt = text("""
            INSERT INTO embedding_migration_audit (
                tenant_id,
                source_version,
                target_version,
                status
            ) VALUES (
                :tenant_id,
                :source_version,
                :target_version,
                'in_progress'
            )
            RETURNING id
        """)
        
        result = await self.session.execute(
            stmt,
            {
                "tenant_id": str(tenant_id),
                "source_version": source_version,
                "target_version": target_version
            }
        )
        
        row = result.fetchone()
        await self.session.commit()
        
        return row.id
    
    async def _update_audit_record(
        self,
        audit_id: int,
        status: MigrationStatus,
        migrated_count: int = 0,
        failed_count: int = 0,
        quality_improvement: Optional[float] = None,
        retrieval_improvement: Optional[float] = None
    ):
        """Update migration audit record."""
        stmt = text("""
            UPDATE embedding_migration_audit
            SET 
                status = :status,
                migrated_count = :migrated_count,
                failed_count = :failed_count,
                avg_quality_improvement = :quality_improvement,
                avg_retrieval_improvement = :retrieval_improvement,
                completed_at = NOW()
            WHERE id = :audit_id
        """)
        
        await self.session.execute(
            stmt,
            {
                "audit_id": audit_id,
                "status": status.value,
                "migrated_count": migrated_count,
                "failed_count": failed_count,
                "quality_improvement": quality_improvement,
                "retrieval_improvement": retrieval_improvement
            }
        )
        
        await self.session.commit()
    
    async def get_migration_status(
        self,
        tenant_id: UUID
    ) -> Dict[str, Any]:
        """
        Get current migration status for tenant.
        
        Returns:
            Dict with version statistics and migration status
        """
        stmt = text("""
            SELECT 
                model_version,
                migration_status,
                COUNT(*) as count,
                AVG(quality_score) as avg_quality,
                MIN(created_at) as first_created,
                MAX(created_at) as last_created
            FROM ga4_embeddings
            WHERE tenant_id = :tenant_id
            GROUP BY model_version, migration_status
            ORDER BY model_version, migration_status
        """)
        
        result = await self.session.execute(
            stmt,
            {"tenant_id": str(tenant_id)}
        )
        
        rows = result.fetchall()
        
        versions = {}
        for row in rows:
            version = row.model_version
            if version not in versions:
                versions[version] = {
                    "version": version,
                    "statuses": {},
                    "total_count": 0
                }
            
            versions[version]["statuses"][row.migration_status] = {
                "count": row.count,
                "avg_quality": float(row.avg_quality) if row.avg_quality else None,
                "first_created": row.first_created.isoformat() if row.first_created else None,
                "last_created": row.last_created.isoformat() if row.last_created else None
            }
            versions[version]["total_count"] += row.count
        
        return {
            "tenant_id": str(tenant_id),
            "versions": list(versions.values())
        }

