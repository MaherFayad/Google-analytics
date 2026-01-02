"""
Chaos Tests: OpenAI Embedding Failures

Implements Task P0-33: Scenario 2 - OpenAI API Fault Injection

Tests system behavior when OpenAI embedding API fails:
- Wrong embedding dimensions (1535 instead of 1536)
- NaN/Inf values in embeddings
- Zero vectors
- API rate limits
- Timeouts

Expected behavior:
- Validation catches dimension mismatches (Task P0-16)
- System rejects invalid embeddings
- Graceful degradation when embeddings fail
- No corrupt data in database
"""

import pytest
import numpy as np
from unittest.mock import patch, AsyncMock

pytestmark = pytest.mark.chaos


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_embedding_dimension_mismatch(inject_fault):
    """
    Test: OpenAI returns wrong embedding dimension
    
    Scenario:
        - OpenAI returns 1535-dim instead of 1536-dim
        - Validation middleware should catch this (Task P0-16)
        - Reject embedding before database insert
        - Log validation error
    
    Expected:
        - status: 'validation_failed'
        - error: Mentions 'dimension_mismatch'
        - No database insert
        - Prometheus metric incremented
    """
    with inject_fault("openai_client", embedding_dim=1535):
        from src.server.services.embedding import quality_checker
        
        # Attempt to generate embedding
        validator = quality_checker.EmbeddingQualityChecker()
        
        # Mock embedding with wrong dimension
        embedding = [0.1] * 1535  # Wrong size!
        
        # Validation should fail
        result = await validator.validate_embedding(
            embedding=embedding,
            expected_dim=1536
        )
        
        # Assertions
        assert result['status'] == 'validation_failed', \
            f"Expected validation_failed, got: {result['status']}"
        
        assert 'dimension' in str(result['errors']).lower(), \
            f"Error should mention dimension: {result['errors']}"
        
        assert result['valid'] is False, \
            "Embedding should be marked as invalid"
        
        # Should report exact dimension mismatch
        assert '1535' in str(result['errors']) and '1536' in str(result['errors']), \
            f"Error should mention expected and actual dimensions: {result['errors']}"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_embedding_contains_nan(inject_fault):
    """
    Test: OpenAI returns embedding with NaN values
    
    Scenario:
        - Embedding contains NaN (not-a-number) values
        - Validation should detect NaN
        - Reject embedding
        - Trigger alert for data quality issue
    
    Expected:
        - Validation catches NaN
        - Embedding rejected
        - Error mentions 'NaN' or 'invalid_values'
        - No database corruption
    """
    from src.server.services.embedding import quality_checker
    
    validator = quality_checker.EmbeddingQualityChecker()
    
    # Create embedding with NaN
    embedding = [0.1] * 1536
    embedding[100] = float('nan')  # Inject NaN
    
    # Validation should fail
    result = await validator.validate_embedding(
        embedding=embedding,
        expected_dim=1536
    )
    
    # Assertions
    assert result['status'] == 'validation_failed', \
        f"Expected validation_failed, got: {result['status']}"
    
    assert 'nan' in str(result['errors']).lower() or 'invalid' in str(result['errors']).lower(), \
        f"Error should mention NaN: {result['errors']}"
    
    assert result['valid'] is False, \
        "Embedding with NaN should be invalid"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_embedding_zero_vector(inject_fault):
    """
    Test: OpenAI returns zero vector (all zeros)
    
    Scenario:
        - Embedding is all zeros (indicates failure)
        - Validation should detect zero vector
        - Reject embedding (useless for similarity search)
        - Retry or fallback
    
    Expected:
        - Zero vector detected
        - Embedding rejected
        - Error mentions 'zero_vector'
        - System retries or falls back
    """
    from src.server.services.embedding import quality_checker
    
    validator = quality_checker.EmbeddingQualityChecker()
    
    # Create zero vector
    embedding = [0.0] * 1536  # All zeros!
    
    # Validation should fail
    result = await validator.validate_embedding(
        embedding=embedding,
        expected_dim=1536
    )
    
    # Assertions
    assert result['status'] == 'validation_failed', \
        f"Expected validation_failed, got: {result['status']}"
    
    assert 'zero' in str(result['errors']).lower() or 'magnitude' in str(result['errors']).lower(), \
        f"Error should mention zero vector: {result['errors']}"
    
    assert result['valid'] is False, \
        "Zero vector should be invalid"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_embedding_magnitude_out_of_range(inject_fault):
    """
    Test: Embedding magnitude is abnormal
    
    Scenario:
        - Embedding has abnormally large or small magnitude
        - Validation should detect outlier
        - Reject embedding (indicates API issue)
        - Alert data quality team
    
    Expected:
        - Magnitude validation catches outlier
        - Embedding rejected
        - Error mentions 'magnitude' or 'norm'
        - Quality score reported
    """
    from src.server.services.embedding import quality_checker
    
    validator = quality_checker.EmbeddingQualityChecker()
    
    # Create embedding with abnormal magnitude
    embedding = [1000.0] * 1536  # Way too large!
    
    # Validation should fail
    result = await validator.validate_embedding(
        embedding=embedding,
        expected_dim=1536,
        magnitude_range=(0.1, 100.0)  # Expected range
    )
    
    # Assertions
    assert result['status'] == 'validation_failed', \
        f"Expected validation_failed, got: {result['status']}"
    
    assert 'magnitude' in str(result['errors']).lower() or 'norm' in str(result['errors']).lower(), \
        f"Error should mention magnitude: {result['errors']}"
    
    assert result['valid'] is False, \
        "Embedding with abnormal magnitude should be invalid"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_embedding_api_rate_limit(inject_fault):
    """
    Test: OpenAI API returns 429 (rate limit exceeded)
    
    Scenario:
        - OpenAI API returns 429 rate limit error
        - System should queue request (Task P0-14)
        - Exponential backoff
        - Eventually succeeds or times out gracefully
    
    Expected:
        - 429 error caught
        - Request queued for retry
        - Exponential backoff applied
        - User notified of delay
    """
    # Mock 429 response
    with patch('openai.AsyncOpenAI.embeddings.create') as mock_create:
        mock_create.side_effect = Exception("Rate limit exceeded (429)")
        
        from src.server.services.embedding import generator
        
        service = generator.EmbeddingGenerator()
        
        # Should handle rate limit
        result = await service.generate_embedding(
            text="test text",
            tenant_id="test-tenant"
        )
        
        # Assertions
        assert result['status'] in ('rate_limited', 'queued', 'failed'), \
            f"Expected rate_limited/queued/failed, got: {result['status']}"
        
        assert 'rate' in str(result.get('errors', [])).lower() or \
               '429' in str(result.get('errors', [])), \
            f"Error should mention rate limit: {result.get('errors')}"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_embedding_api_timeout(inject_fault):
    """
    Test: OpenAI API times out
    
    Scenario:
        - OpenAI API request times out (>30s)
        - System should cancel request
        - Retry with exponential backoff
        - Eventually fail gracefully
    
    Expected:
        - Timeout error caught
        - Request cancelled
        - Retry attempted
        - User notified
    """
    # Mock timeout
    with patch('openai.AsyncOpenAI.embeddings.create') as mock_create:
        async def timeout_side_effect(*args, **kwargs):
            import asyncio
            await asyncio.sleep(100)  # Simulate timeout
        
        mock_create.side_effect = timeout_side_effect
        
        from src.server.services.embedding import generator
        
        service = generator.EmbeddingGenerator(timeout=1)  # 1 second timeout
        
        # Should timeout
        result = await service.generate_embedding(
            text="test text",
            tenant_id="test-tenant"
        )
        
        # Assertions
        assert result['status'] in ('timeout', 'failed'), \
            f"Expected timeout/failed, got: {result['status']}"
        
        assert 'timeout' in str(result.get('errors', [])).lower(), \
            f"Error should mention timeout: {result.get('errors')}"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_batch_embedding_partial_failure(inject_fault):
    """
    Test: Batch embedding generation with partial failures
    
    Scenario:
        - Generate embeddings for multiple texts
        - Some succeed, some fail
        - System should handle partial success
        - Return successful embeddings
        - Report failures separately
    
    Expected:
        - Partial success handled
        - Successful embeddings stored
        - Failed embeddings reported
        - No data loss
    """
    from src.server.services.embedding import generator
    
    service = generator.EmbeddingGenerator()
    
    # Mock some successes and some failures
    call_count = 0
    
    async def mixed_results(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        
        if call_count % 2 == 0:
            # Success
            return {
                'data': [{'embedding': [0.1] * 1536}],
                'usage': {'total_tokens': 10}
            }
        else:
            # Failure
            raise Exception("Embedding generation failed")
    
    with patch('openai.AsyncOpenAI.embeddings.create', side_effect=mixed_results):
        # Generate batch
        texts = [f"text {i}" for i in range(10)]
        
        result = await service.generate_batch(
            texts=texts,
            tenant_id="test-tenant"
        )
        
        # Assertions
        assert result['status'] in ('partial', 'partial_success'), \
            f"Expected partial status, got: {result['status']}"
        
        assert result['successful_count'] > 0, \
            "Should have some successful embeddings"
        
        assert result['failed_count'] > 0, \
            "Should have some failed embeddings"
        
        assert result['successful_count'] + result['failed_count'] == 10, \
            "Total should equal input count"

