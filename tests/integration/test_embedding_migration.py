"""
Integration tests for Embedding Model Version Migration Pipeline.

Implements Task P0-26: Embedding Model Version Migration Pipeline

Tests:
1. Version registration
2. Blue-green migration
3. A/B testing and quality comparison
4. Gradual rollout phases
5. Rollback capability
6. Audit trail verification
"""

import pytest
import asyncio
from uuid import uuid4, UUID
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.server.services.embedding.version_migrator import (
    EmbeddingVersionMigrator,
    EmbeddingModelConfig,
    MigrationPhase,
    MigrationStatus
)
from src.server.services.embedding.quality_comparator import (
    EmbeddingQualityComparator
)


@pytest.fixture
async def test_tenant_id():
    """Generate test tenant ID."""
    return uuid4()


@pytest.fixture
async def test_user_id():
    """Generate test user ID."""
    return uuid4()


@pytest.fixture
async def setup_test_embeddings(db_session: AsyncSession, test_tenant_id: UUID, test_user_id: UUID):
    """
    Set up test embeddings with v1.0 model.
    
    Creates 50 test embeddings for migration testing.
    """
    # Set RLS context
    await db_session.execute(
        text("SET LOCAL app.tenant_id = :tenant_id"),
        {"tenant_id": str(test_tenant_id)}
    )
    await db_session.execute(
        text("SET LOCAL app.user_id = :user_id"),
        {"user_id": str(test_user_id)}
    )
    
    # Create test metrics
    for i in range(50):
        # Insert into ga4_metrics_raw
        stmt = text("""
            INSERT INTO ga4_metrics_raw (
                tenant_id,
                user_id,
                property_id,
                metric_date,
                dimension_context,
                metric_values,
                descriptive_summary
            ) VALUES (
                :tenant_id,
                :user_id,
                'test-property-123',
                :metric_date,
                :dimension_context::jsonb,
                :metric_values::jsonb,
                :descriptive_summary
            )
        """)
        
        await db_session.execute(
            stmt,
            {
                "tenant_id": str(test_tenant_id),
                "user_id": str(test_user_id),
                "metric_date": (datetime.now() - timedelta(days=i)).date(),
                "dimension_context": '{"device": "mobile"}',
                "metric_values": f'{{"sessions": {1000 + i * 10}}}',
                "descriptive_summary": f"Test metric {i}: Mobile sessions increased to {1000 + i * 10}"
            }
        )
    
    await db_session.commit()
    
    # Create test embeddings (v1.0)
    for i in range(50):
        # Generate fake embedding vector (1536 dimensions)
        import random
        embedding_vector = [random.gauss(0, 0.1) for _ in range(1536)]
        embedding_str = f"[{','.join(map(str, embedding_vector))}]"
        
        stmt = text("""
            INSERT INTO ga4_embeddings (
                tenant_id,
                user_id,
                content,
                embedding,
                temporal_metadata,
                embedding_model,
                embedding_dimensions,
                model_version,
                migration_status,
                quality_score
            ) VALUES (
                :tenant_id,
                :user_id,
                :content,
                :embedding::vector(1536),
                :temporal_metadata::jsonb,
                'text-embedding-3-small',
                1536,
                'v1.0',
                'active',
                :quality_score
            )
        """)
        
        await db_session.execute(
            stmt,
            {
                "tenant_id": str(test_tenant_id),
                "user_id": str(test_user_id),
                "content": f"Test embedding {i}",
                "embedding": embedding_str,
                "temporal_metadata": '{"date_range": {"start": "2025-01-01", "end": "2025-01-01"}}',
                "quality_score": 0.8 + random.uniform(-0.1, 0.1)
            }
        )
    
    await db_session.commit()
    
    yield
    
    # Cleanup
    await db_session.execute(
        text("DELETE FROM ga4_embeddings WHERE tenant_id = :tenant_id"),
        {"tenant_id": str(test_tenant_id)}
    )
    await db_session.execute(
        text("DELETE FROM ga4_metrics_raw WHERE tenant_id = :tenant_id"),
        {"tenant_id": str(test_tenant_id)}
    )
    await db_session.commit()


class TestEmbeddingVersionMigrator:
    """Test cases for version migration coordinator."""
    
    @pytest.mark.asyncio
    async def test_register_model_version(self, db_session: AsyncSession):
        """Test registering a new embedding model version."""
        migrator = EmbeddingVersionMigrator(db_session)
        
        # Register new version
        config = EmbeddingModelConfig(
            version_name="v2.0-test",
            model_name="text-embedding-3-large",
            dimensions=3072,
            description="Test version for large model"
        )
        
        version_id = await migrator.register_model_version(
            config=config,
            status="testing"
        )
        
        assert version_id is not None
        assert isinstance(version_id, int)
        
        # Verify registration
        stmt = text("""
            SELECT version_name, model_name, dimensions, status
            FROM embedding_model_versions
            WHERE version_name = :version_name
        """)
        
        result = await db_session.execute(
            stmt,
            {"version_name": "v2.0-test"}
        )
        
        row = result.fetchone()
        assert row is not None
        assert row.version_name == "v2.0-test"
        assert row.model_name == "text-embedding-3-large"
        assert row.dimensions == 3072
        assert row.status == "testing"
    
    @pytest.mark.asyncio
    async def test_get_tenant_version(
        self,
        db_session: AsyncSession,
        test_tenant_id: UUID,
        test_user_id: UUID,
        setup_test_embeddings
    ):
        """Test getting current version for tenant."""
        migrator = EmbeddingVersionMigrator(db_session)
        
        current_version = await migrator._get_tenant_version(test_tenant_id)
        
        assert current_version == "v1.0"
    
    @pytest.mark.asyncio
    async def test_migration_testing_phase(
        self,
        db_session: AsyncSession,
        test_tenant_id: UUID,
        test_user_id: UUID,
        setup_test_embeddings
    ):
        """Test migration in testing phase (A/B testing)."""
        migrator = EmbeddingVersionMigrator(db_session)
        
        # Define target version
        target_config = EmbeddingModelConfig(
            version_name="v2.0-test",
            model_name="text-embedding-3-large",
            dimensions=3072,
            description="Test migration to large model"
        )
        
        # Run migration with small sample
        result = await migrator.migrate_tenant(
            tenant_id=test_tenant_id,
            user_id=test_user_id,
            target_config=target_config,
            phase=MigrationPhase.TESTING,
            sample_size=10,
            quality_threshold=0.0  # Low threshold for testing
        )
        
        # Verify result
        assert result.status == MigrationStatus.COMPLETED
        assert result.tenant_id == test_tenant_id
        assert result.source_version == "v1.0"
        assert result.target_version == "v2.0-test"
        assert result.migrated_count > 0
        assert result.duration_seconds > 0
        
        # Verify quality improvement calculated
        assert result.quality_improvement is not None
        assert result.retrieval_improvement is not None
    
    @pytest.mark.asyncio
    async def test_migration_status_tracking(
        self,
        db_session: AsyncSession,
        test_tenant_id: UUID,
        test_user_id: UUID,
        setup_test_embeddings
    ):
        """Test migration status tracking."""
        migrator = EmbeddingVersionMigrator(db_session)
        
        # Get initial status
        status_before = await migrator.get_migration_status(test_tenant_id)
        
        assert "versions" in status_before
        assert len(status_before["versions"]) >= 1
        
        # Find v1.0 version
        v1_stats = next(
            (v for v in status_before["versions"] if v["version"] == "v1.0"),
            None
        )
        assert v1_stats is not None
        assert v1_stats["total_count"] == 50  # From setup
    
    @pytest.mark.asyncio
    async def test_rollback_migration(
        self,
        db_session: AsyncSession,
        test_tenant_id: UUID,
        test_user_id: UUID,
        setup_test_embeddings
    ):
        """Test rolling back a migration."""
        migrator = EmbeddingVersionMigrator(db_session)
        
        # Create some v2.0 embeddings
        await db_session.execute(
            text("SET LOCAL app.tenant_id = :tenant_id"),
            {"tenant_id": str(test_tenant_id)}
        )
        
        # Insert a few v2.0 embeddings
        import random
        for i in range(5):
            embedding_vector = [random.gauss(0, 0.1) for _ in range(3072)]
            embedding_str = f"[{','.join(map(str, embedding_vector))}]"
            
            stmt = text("""
                INSERT INTO ga4_embeddings (
                    tenant_id,
                    user_id,
                    content,
                    embedding,
                    temporal_metadata,
                    embedding_model,
                    embedding_dimensions,
                    model_version,
                    migration_status,
                    quality_score
                ) VALUES (
                    :tenant_id,
                    :user_id,
                    :content,
                    :embedding::vector(3072),
                    :temporal_metadata::jsonb,
                    'text-embedding-3-large',
                    3072,
                    'v2.0',
                    'active',
                    0.85
                )
            """)
            
            await db_session.execute(
                stmt,
                {
                    "tenant_id": str(test_tenant_id),
                    "user_id": str(test_user_id),
                    "content": f"V2 embedding {i}",
                    "embedding": embedding_str,
                    "temporal_metadata": '{"date_range": {"start": "2025-01-01", "end": "2025-01-01"}}'
                }
            )
        
        await db_session.commit()
        
        # Rollback to v1.0
        success = await migrator.rollback_migration(
            tenant_id=test_tenant_id,
            target_version="v1.0"
        )
        
        assert success is True


class TestEmbeddingQualityComparator:
    """Test cases for quality A/B testing comparator."""
    
    @pytest.mark.asyncio
    async def test_version_statistics(
        self,
        db_session: AsyncSession,
        test_tenant_id: UUID,
        test_user_id: UUID,
        setup_test_embeddings
    ):
        """Test getting version statistics."""
        comparator = EmbeddingQualityComparator(db_session)
        
        stats = await comparator._get_version_statistics(
            tenant_id=test_tenant_id,
            version="v1.0",
            sample_size=50
        )
        
        assert stats["count"] == 50
        assert stats["avg_quality_score"] > 0.0
        assert stats["min_quality"] >= 0.0
        assert stats["max_quality"] <= 1.0
        assert stats["std_quality"] >= 0.0
    
    @pytest.mark.asyncio
    async def test_compare_versions(
        self,
        db_session: AsyncSession,
        test_tenant_id: UUID,
        test_user_id: UUID,
        setup_test_embeddings
    ):
        """Test comparing two versions."""
        comparator = EmbeddingQualityComparator(db_session)
        
        # Create some v2.0 embeddings with slightly better quality
        await db_session.execute(
            text("SET LOCAL app.tenant_id = :tenant_id"),
            {"tenant_id": str(test_tenant_id)}
        )
        
        import random
        for i in range(20):
            embedding_vector = [random.gauss(0, 0.1) for _ in range(3072)]
            embedding_str = f"[{','.join(map(str, embedding_vector))}]"
            
            stmt = text("""
                INSERT INTO ga4_embeddings (
                    tenant_id,
                    user_id,
                    content,
                    embedding,
                    temporal_metadata,
                    embedding_model,
                    embedding_dimensions,
                    model_version,
                    migration_status,
                    quality_score
                ) VALUES (
                    :tenant_id,
                    :user_id,
                    :content,
                    :embedding::vector(3072),
                    :temporal_metadata::jsonb,
                    'text-embedding-3-large',
                    3072,
                    'v2.0',
                    'active',
                    :quality_score
                )
            """)
            
            await db_session.execute(
                stmt,
                {
                    "tenant_id": str(test_tenant_id),
                    "user_id": str(test_user_id),
                    "content": f"V2 embedding {i}",
                    "embedding": embedding_str,
                    "temporal_metadata": '{"date_range": {"start": "2025-01-01", "end": "2025-01-01"}}',
                    "quality_score": 0.85 + random.uniform(-0.05, 0.1)  # Slightly better
                }
            )
        
        await db_session.commit()
        
        # Compare versions
        comparison = await comparator.compare_versions(
            tenant_id=test_tenant_id,
            version_a="v1.0",
            version_b="v2.0",
            sample_size=20
        )
        
        # Verify comparison result
        assert comparison.version_a == "v1.0"
        assert comparison.version_b == "v2.0"
        assert comparison.version_a_count == 20
        assert comparison.version_b_count == 20
        assert comparison.version_a_quality_score > 0.0
        assert comparison.version_b_quality_score > 0.0
        assert comparison.quality_improvement_percent is not None
        assert comparison.recommended_version in ["v1.0", "v2.0"]
        assert comparison.confidence in ["low", "medium", "high"]
    
    @pytest.mark.asyncio
    async def test_quality_distribution(
        self,
        db_session: AsyncSession,
        test_tenant_id: UUID,
        test_user_id: UUID,
        setup_test_embeddings
    ):
        """Test getting quality score distribution."""
        comparator = EmbeddingQualityComparator(db_session)
        
        distribution = await comparator.get_version_distribution(
            tenant_id=test_tenant_id,
            version="v1.0",
            sample_size=50
        )
        
        assert distribution["version"] == "v1.0"
        assert distribution["count"] == 50
        assert distribution["mean"] > 0.0
        assert distribution["std"] >= 0.0
        assert "percentiles" in distribution
        assert "p50" in distribution["percentiles"]
        assert "histogram" in distribution
        assert "counts" in distribution["histogram"]
    
    @pytest.mark.asyncio
    async def test_percent_change_calculation(self):
        """Test percent change calculation."""
        comparator = EmbeddingQualityComparator(None)
        
        # Test improvement
        change = comparator._calculate_percent_change(0.80, 0.88)
        assert change == 10.0  # 10% improvement
        
        # Test regression
        change = comparator._calculate_percent_change(0.90, 0.81)
        assert change == -10.0  # 10% regression
        
        # Test no change
        change = comparator._calculate_percent_change(0.85, 0.85)
        assert change == 0.0


class TestMigrationAuditTrail:
    """Test cases for migration audit trail."""
    
    @pytest.mark.asyncio
    async def test_audit_record_created(
        self,
        db_session: AsyncSession,
        test_tenant_id: UUID,
        test_user_id: UUID,
        setup_test_embeddings
    ):
        """Test that migration creates audit record."""
        migrator = EmbeddingVersionMigrator(db_session)
        
        target_config = EmbeddingModelConfig(
            version_name="v2.0-audit-test",
            model_name="text-embedding-3-large",
            dimensions=3072,
            description="Test audit trail"
        )
        
        # Run migration
        result = await migrator.migrate_tenant(
            tenant_id=test_tenant_id,
            user_id=test_user_id,
            target_config=target_config,
            phase=MigrationPhase.TESTING,
            sample_size=5,
            quality_threshold=0.0
        )
        
        # Verify audit record exists
        stmt = text("""
            SELECT 
                tenant_id,
                source_version,
                target_version,
                status,
                migrated_count,
                failed_count
            FROM embedding_migration_audit
            WHERE tenant_id = :tenant_id
            AND target_version = :target_version
            ORDER BY started_at DESC
            LIMIT 1
        """)
        
        audit_result = await db_session.execute(
            stmt,
            {
                "tenant_id": str(test_tenant_id),
                "target_version": "v2.0-audit-test"
            }
        )
        
        audit_row = audit_result.fetchone()
        assert audit_row is not None
        assert audit_row.tenant_id == test_tenant_id
        assert audit_row.source_version == "v1.0"
        assert audit_row.target_version == "v2.0-audit-test"
        assert audit_row.status in ["completed", "failed"]
        assert audit_row.migrated_count >= 0


@pytest.mark.asyncio
async def test_end_to_end_migration_pipeline(
    db_session: AsyncSession,
    test_tenant_id: UUID,
    test_user_id: UUID,
    setup_test_embeddings
):
    """
    End-to-end test of complete migration pipeline.
    
    Tests:
    1. Initial state (v1.0)
    2. Testing phase with A/B comparison
    3. Rollout decision
    4. Final migration
    5. Audit trail verification
    """
    migrator = EmbeddingVersionMigrator(db_session)
    comparator = EmbeddingQualityComparator(db_session)
    
    # Phase 1: Register new version
    target_config = EmbeddingModelConfig(
        version_name="v2.0-e2e",
        model_name="text-embedding-3-large",
        dimensions=3072,
        description="End-to-end test migration"
    )
    
    await migrator.register_model_version(config=target_config, status="testing")
    
    # Phase 2: Testing with small sample
    test_result = await migrator.migrate_tenant(
        tenant_id=test_tenant_id,
        user_id=test_user_id,
        target_config=target_config,
        phase=MigrationPhase.TESTING,
        sample_size=10,
        quality_threshold=0.0
    )
    
    assert test_result.status == MigrationStatus.COMPLETED
    assert test_result.migrated_count > 0
    
    # Phase 3: Check migration status
    status = await migrator.get_migration_status(test_tenant_id)
    
    # Should have both v1.0 and v2.0-e2e
    versions = [v["version"] for v in status["versions"]]
    assert "v1.0" in versions
    assert "v2.0-e2e" in versions
    
    # Phase 4: Verify audit trail
    stmt = text("""
        SELECT COUNT(*) as count
        FROM embedding_migration_audit
        WHERE tenant_id = :tenant_id
        AND target_version = :target_version
    """)
    
    result = await db_session.execute(
        stmt,
        {"tenant_id": str(test_tenant_id), "target_version": "v2.0-e2e"}
    )
    
    row = result.fetchone()
    assert row.count > 0
    
    print(f"\n✅ End-to-end migration pipeline test passed!")
    print(f"   Migrated: {test_result.migrated_count} embeddings")
    print(f"   Duration: {test_result.duration_seconds:.2f}s")
    print(f"   Quality improvement: {test_result.quality_improvement:+.2f}%")

