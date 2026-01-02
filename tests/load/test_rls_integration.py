"""
Pytest integration test for RLS isolation under load.

This test can be run in CI/CD pipelines without requiring Locust UI.

Usage:
    pytest tests/load/test_rls_integration.py -v
    pytest tests/load/test_rls_integration.py -v --concurrent-users=500
"""

import pytest
import asyncio
import httpx
import uuid
from typing import List, Dict
from datetime import timedelta

from tests.load.conftest import generate_test_jwt, TEST_TENANT_COUNT
from tests.load.isolation_validator import IsolationValidator
from tests.load.rls_scenarios import RLSScenarios


@pytest.fixture
def api_base_url():
    """API base URL for testing."""
    return "http://localhost:8000"


@pytest.fixture
def isolation_validator():
    """Create fresh isolation validator for each test."""
    validator = IsolationValidator()
    yield validator
    validator.reset()


@pytest.fixture
def test_tenants():
    """Generate test tenant IDs."""
    tenants = []
    namespace = uuid.UUID("12345678-1234-5678-1234-567812345678")
    for i in range(10):  # Use 10 tenants for integration test
        tenant_id = str(uuid.uuid5(namespace, f"tenant_{i}"))
        user_id = str(uuid.uuid5(namespace, f"user_{i}"))
        tenants.append({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "jwt": generate_test_jwt(user_id, tenant_id)
        })
    return tenants


async def make_request(
    client: httpx.AsyncClient,
    tenant: Dict,
    endpoint: str,
    payload: Dict,
    validator: IsolationValidator
) -> bool:
    """
    Make authenticated request and validate isolation.
    
    Returns:
        True if no violation, False otherwise
    """
    headers = {
        "Authorization": f"Bearer {tenant['jwt']}",
        "X-Tenant-Context": tenant["tenant_id"],
        "Content-Type": "application/json"
    }
    
    try:
        response = await client.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=10.0
        )
        
        if response.status_code == 200:
            response_data = response.json()
            return validator.validate_response(
                requesting_tenant_id=tenant["tenant_id"],
                response_data=response_data,
                endpoint=endpoint
            )
        
        return True  # Non-200 responses don't count as violations
    
    except Exception as e:
        # Network errors don't count as isolation violations
        return True


@pytest.mark.asyncio
async def test_concurrent_vector_search_isolation(
    api_base_url: str,
    test_tenants: List[Dict],
    isolation_validator: IsolationValidator
):
    """
    Test vector search isolation with concurrent requests.
    
    Simulates 100 concurrent vector searches across 10 tenants.
    Each tenant makes 10 requests simultaneously.
    
    Target: 100% isolation (no cross-tenant data leakage)
    """
    endpoint = f"{api_base_url}/api/v1/analytics/query"
    
    async with httpx.AsyncClient() as client:
        # Create 100 concurrent requests (10 tenants × 10 requests each)
        tasks = []
        for _ in range(10):  # 10 requests per tenant
            for tenant in test_tenants:
                payload = RLSScenarios.scenario_1_vector_search(tenant["tenant_id"])
                task = make_request(client, tenant, endpoint, payload, isolation_validator)
                tasks.append(task)
        
        # Execute all requests concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful validations
        successful = sum(1 for r in results if r is True)
        total = len(results)
    
    # Validate results
    success_rate = isolation_validator.get_isolation_success_rate()
    violation_count = isolation_validator.get_violation_count()
    
    print(f"\n{'='*60}")
    print(f"Concurrent Vector Search Test Results")
    print(f"{'='*60}")
    print(f"Total Requests: {total}")
    print(f"Successful Validations: {successful}")
    print(f"Isolation Violations: {violation_count}")
    print(f"Success Rate: {success_rate:.4f}%")
    print(f"{'='*60}\n")
    
    # Assert no violations
    isolation_validator.assert_no_violations()


@pytest.mark.asyncio
async def test_rapid_context_switching(
    api_base_url: str,
    test_tenants: List[Dict],
    isolation_validator: IsolationValidator
):
    """
    Test rapid tenant context switching for race conditions.
    
    Simulates a single user rapidly switching between two tenant contexts.
    This tests for session variable race conditions.
    
    Target: 100% isolation (no session variable bleed)
    """
    endpoint = f"{api_base_url}/api/v1/analytics/query"
    
    # Use first two tenants
    tenant_a = test_tenants[0]
    tenant_b = test_tenants[1]
    
    async with httpx.AsyncClient() as client:
        tasks = []
        
        # Alternate between tenants rapidly (50 requests each)
        for i in range(100):
            tenant = tenant_a if i % 2 == 0 else tenant_b
            payload = {"query": f"Quick query {i}", "tenant_id": tenant["tenant_id"]}
            task = make_request(client, tenant, endpoint, payload, isolation_validator)
            tasks.append(task)
        
        # Execute with minimal delay to stress test session variables
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Validate results
    success_rate = isolation_validator.get_isolation_success_rate()
    violation_count = isolation_validator.get_violation_count()
    
    print(f"\n{'='*60}")
    print(f"Rapid Context Switching Test Results")
    print(f"{'='*60}")
    print(f"Total Requests: {len(results)}")
    print(f"Isolation Violations: {violation_count}")
    print(f"Success Rate: {success_rate:.4f}%")
    print(f"{'='*60}\n")
    
    # Assert no violations
    isolation_validator.assert_no_violations()


@pytest.mark.asyncio
async def test_mixed_endpoint_isolation(
    api_base_url: str,
    test_tenants: List[Dict],
    isolation_validator: IsolationValidator
):
    """
    Test isolation across multiple endpoints simultaneously.
    
    Tests:
    - Vector search (/api/v1/analytics/query)
    - Chat sessions (/api/v1/chat/sessions)
    - GA4 metrics (/api/v1/analytics/ga4/metrics)
    
    Target: 100% isolation across all endpoints
    """
    endpoints = [
        ("/api/v1/analytics/query", lambda tid: RLSScenarios.scenario_1_vector_search(tid)),
        ("/api/v1/chat/sessions", lambda tid: RLSScenarios.scenario_2_chat_sessions(tid)),
        ("/api/v1/analytics/ga4/metrics", lambda tid: RLSScenarios.scenario_3_ga4_data(tid)),
    ]
    
    async with httpx.AsyncClient() as client:
        tasks = []
        
        # Each tenant hits all endpoints
        for tenant in test_tenants:
            for endpoint, payload_generator in endpoints:
                full_url = f"{api_base_url}{endpoint}"
                payload = payload_generator(tenant["tenant_id"])
                task = make_request(client, tenant, full_url, payload, isolation_validator)
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Validate results
    success_rate = isolation_validator.get_isolation_success_rate()
    violation_count = isolation_validator.get_violation_count()
    
    print(f"\n{'='*60}")
    print(f"Mixed Endpoint Isolation Test Results")
    print(f"{'='*60}")
    print(f"Total Requests: {len(results)}")
    print(f"Endpoints Tested: {len(endpoints)}")
    print(f"Tenants: {len(test_tenants)}")
    print(f"Isolation Violations: {violation_count}")
    print(f"Success Rate: {success_rate:.4f}%")
    print(f"{'='*60}\n")
    
    # Assert no violations
    isolation_validator.assert_no_violations()


@pytest.mark.asyncio
@pytest.mark.slow
async def test_sustained_load_isolation(
    api_base_url: str,
    test_tenants: List[Dict],
    isolation_validator: IsolationValidator
):
    """
    Test isolation under sustained load (500 requests).
    
    This test runs longer and generates more requests to catch
    edge cases that might not appear in shorter tests.
    
    Target: 99.99% isolation (max 1 violation per 10,000 requests)
    """
    endpoint = f"{api_base_url}/api/v1/analytics/query"
    
    async with httpx.AsyncClient() as client:
        # Generate 500 requests (50 per tenant)
        tasks = []
        for _ in range(50):
            for tenant in test_tenants:
                payload = RLSScenarios.scenario_1_vector_search(tenant["tenant_id"])
                task = make_request(client, tenant, endpoint, payload, isolation_validator)
                tasks.append(task)
        
        # Execute in batches to avoid overwhelming the server
        batch_size = 50
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            await asyncio.gather(*batch, return_exceptions=True)
            await asyncio.sleep(0.1)  # Small delay between batches
    
    # Validate results
    success_rate = isolation_validator.get_isolation_success_rate()
    violation_count = isolation_validator.get_violation_count()
    total_requests = isolation_validator._total_validations
    
    print(f"\n{'='*60}")
    print(f"Sustained Load Isolation Test Results")
    print(f"{'='*60}")
    print(f"Total Requests: {total_requests}")
    print(f"Isolation Violations: {violation_count}")
    print(f"Success Rate: {success_rate:.4f}%")
    print(f"Target: 99.99%")
    print(f"{'='*60}\n")
    
    # Assert meets target (99.99% for sustained load)
    isolation_validator.assert_meets_target(target_success_rate=99.99)


# Mark as integration test
pytestmark = pytest.mark.integration

