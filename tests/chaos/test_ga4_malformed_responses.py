"""
Chaos Tests: GA4 API Malformed Responses

Implements Task P0-33: Scenario 1 - GA4 API Fault Injection

Tests system behavior when GA4 API returns malformed data:
- Invalid UTF-8 encoding
- Malformed JSON
- Missing required fields
- Unexpected data types

Expected behavior:
- System gracefully degrades
- Falls back to cached data
- Logs errors appropriately
- No unhandled exceptions
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from httpx import Response

# Chaos test marker
pytest mark = pytest.mark.chaos


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_ga4_malformed_utf8(inject_fault):
    """
    Test: GA4 API returns invalid UTF-8 encoding
    
    Scenario:
        - GA4 API returns response with invalid UTF-8 bytes
        - System should detect encoding error
        - Fallback to cached data
        - Log error for monitoring
    
    Expected:
        - status: 'degraded' (not 'failed')
        - errors: Contains 'encoding_error'
        - fallback_data: Not None (uses cache)
        - circuit_breaker: Opens after threshold
    """
    # Invalid UTF-8 bytes
    malformed_response = b'\xff\xfe Invalid UTF-8 \xc3\x28'
    
    with inject_fault("ga4_client", response=malformed_response):
        # Import service (mock will be active)
        from src.server.services.ga4 import resilient_client
        
        # Attempt to fetch GA4 data
        client = resilient_client.ResilientGA4Client(
            property_id="12345",
            credentials={}
        )
        
        # Should gracefully handle
        result = await client.run_report(
            dimensions=["date"],
            metrics=["sessions"]
        )
        
        # Assertions
        assert result['status'] in ('degraded', 'cached'), \
            f"Expected degraded/cached status, got: {result['status']}"
        
        assert result.get('data') is not None, \
            "Should return fallback data"
        
        assert 'errors' in result, \
            "Should include error details"
        
        # Should not crash
        assert 'encoding_error' in str(result.get('errors', [])).lower() or \
               'decode' in str(result.get('errors', [])).lower(), \
            "Error should mention encoding/decode issue"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_ga4_malformed_json(inject_fault):
    """
    Test: GA4 API returns invalid JSON
    
    Scenario:
        - GA4 API returns 200 OK but body is not valid JSON
        - System should detect JSON parse error
        - Fallback to cached data
        - Retry with exponential backoff
    
    Expected:
        - JSON parse error caught
        - Retry mechanism triggers
        - Eventually falls back to cache
        - No unhandled exceptions
    """
    malformed_json = b'{"incomplete": "json", invalid}'
    
    with inject_fault("ga4_client", response=malformed_json):
        from src.server.services.ga4 import resilient_client
        
        client = resilient_client.ResilientGA4Client(
            property_id="12345",
            credentials={}
        )
        
        # Should handle JSON parse error
        result = await client.run_report(
            dimensions=["date"],
            metrics=["sessions"]
        )
        
        # Assertions
        assert result['status'] != 'success', \
            "Should not report success with malformed JSON"
        
        assert result['status'] in ('degraded', 'cached', 'failed_with_cache'), \
            f"Expected degraded/cached status, got: {result['status']}"
        
        # Should include error information
        errors = result.get('errors', [])
        assert len(errors) > 0, "Should report errors"
        
        # Should mention JSON parsing issue
        error_messages = ' '.join(str(e) for e in errors).lower()
        assert 'json' in error_messages or 'parse' in error_messages, \
            f"Error should mention JSON parsing: {errors}"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_ga4_missing_required_fields(inject_fault):
    """
    Test: GA4 API returns JSON with missing required fields
    
    Scenario:
        - GA4 API returns valid JSON but missing 'rows' field
        - System should detect schema violation
        - Return partial data or fallback
        - Log validation error
    
    Expected:
        - Schema validation catches missing fields
        - Graceful degradation
        - Clear error message
        - No crashes
    """
    incomplete_response = b'{"dimensionHeaders": [], "metricHeaders": []}'  # Missing 'rows'
    
    with inject_fault("ga4_client", response=incomplete_response):
        from src.server.services.ga4 import resilient_client
        
        client = resilient_client.ResilientGA4Client(
            property_id="12345",
            credentials={}
        )
        
        # Should handle missing fields
        result = await client.run_report(
            dimensions=["date"],
            metrics=["sessions"]
        )
        
        # Assertions
        assert result['status'] in ('degraded', 'partial', 'cached'), \
            f"Expected degraded/partial/cached, got: {result['status']}"
        
        # Should report validation error
        assert 'errors' in result, "Should include error details"
        
        # Error should mention missing field
        errors_str = str(result['errors']).lower()
        assert 'rows' in errors_str or 'missing' in errors_str or 'schema' in errors_str, \
            f"Error should mention missing field: {result['errors']}"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_ga4_unexpected_data_types(inject_fault):
    """
    Test: GA4 API returns unexpected data types (strings instead of numbers)
    
    Scenario:
        - GA4 API returns metric values as strings: "1234" instead of 1234
        - System should coerce types or reject
        - Maintain data integrity
        - Don't propagate bad data to frontend
    
    Expected:
        - Type validation catches mismatches
        - Coercion applied where safe
        - Invalid data rejected
        - Clear error messages
    """
    type_mismatch_response = b'''{
        "dimensionHeaders": [{"name": "date"}],
        "metricHeaders": [{"name": "sessions", "type": "TYPE_INTEGER"}],
        "rows": [
            {
                "dimensionValues": [{"value": "20250101"}],
                "metricValues": [{"value": "not_a_number"}]
            }
        ]
    }'''
    
    with inject_fault("ga4_client", response=type_mismatch_response):
        from src.server.services.ga4 import resilient_client
        
        client = resilient_client.ResilientGA4Client(
            property_id="12345",
            credentials={}
        )
        
        # Should handle type mismatches
        result = await client.run_report(
            dimensions=["date"],
            metrics=["sessions"]
        )
        
        # Assertions
        assert result['status'] in ('degraded', 'validation_failed', 'partial'), \
            f"Expected degraded/validation_failed, got: {result['status']}"
        
        # Should report type error
        assert 'errors' in result, "Should include error details"
        
        # Error should mention type or validation
        errors_str = str(result['errors']).lower()
        assert 'type' in errors_str or 'validation' in errors_str or 'convert' in errors_str, \
            f"Error should mention type/validation: {result['errors']}"


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_ga4_circuit_breaker_opens(inject_fault, circuit_breaker_monitor):
    """
    Test: Circuit breaker opens after repeated GA4 failures
    
    Scenario:
        - GA4 API returns malformed responses repeatedly
        - After N failures, circuit breaker should open
        - Subsequent requests should fail fast
        - Circuit breaker should close after recovery period
    
    Expected:
        - Circuit breaker opens after threshold (e.g., 5 failures)
        - Requests fail immediately while open
        - Circuit breaker closes after timeout
        - System recovers automatically
    """
    malformed_response = b'malformed data'
    
    with inject_fault("ga4_client", response=malformed_response):
        with circuit_breaker_monitor() as monitor:
            from src.server.services.ga4 import resilient_client
            
            client = resilient_client.ResilientGA4Client(
                property_id="12345",
                credentials={},
                circuit_breaker_threshold=5  # Open after 5 failures
            )
            
            # Trigger multiple failures
            for i in range(6):
                result = await client.run_report(
                    dimensions=["date"],
                    metrics=["sessions"]
                )
                
                # First 5 should attempt request
                # 6th should fail fast (circuit open)
                if i < 5:
                    assert result['status'] in ('degraded', 'failed'), \
                        f"Request {i+1} should attempt and fail"
                else:
                    assert result['status'] == 'circuit_open', \
                        f"Request {i+1} should fail fast (circuit open)"
            
            # Check circuit breaker opened
            assert monitor.is_open("ga4_client"), \
                "Circuit breaker should be open after threshold"
            
            # TODO: Test circuit breaker closes after recovery
            # (Would require waiting for timeout and successful request)


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_ga4_recovery_after_fault(inject_fault, wait_for_recovery):
    """
    Test: System recovers after GA4 fault is removed
    
    Scenario:
        - GA4 API fails temporarily
        - Fault is removed
        - System should detect recovery
        - Resume normal operations
    
    Expected:
        - System recovers within 60 seconds
        - Circuit breaker closes
        - Requests succeed normally
        - Cache is refreshed
    """
    malformed_response = b'temporary failure'
    
    # Inject fault temporarily
    with inject_fault("ga4_client", response=malformed_response):
        from src.server.services.ga4 import resilient_client
        
        client = resilient_client.ResilientGA4Client(
            property_id="12345",
            credentials={}
        )
        
        # Should fail during fault
        result = await client.run_report(
            dimensions=["date"],
            metrics=["sessions"]
        )
        
        assert result['status'] != 'success', \
            "Should fail during fault injection"
    
    # Fault removed - system should recover
    async with wait_for_recovery(service="ga4_client", timeout=60) as recovery:
        # System should recover
        result = await client.run_report(
            dimensions=["date"],
            metrics=["sessions"]
        )
        
        # Check recovery
        assert recovery.recovered, \
            f"System should recover within 60s"
        
        assert result['status'] == 'success', \
            f"Requests should succeed after recovery, got: {result['status']}"
        
        assert recovery.recovery_time < 60, \
            f"Recovery took too long: {recovery.recovery_time}s"

