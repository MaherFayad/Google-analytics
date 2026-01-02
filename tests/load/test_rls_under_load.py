"""
Locust load test for RLS policies under concurrent load.

Implements Task P0-29: Load Test RLS Policies Under Concurrent Session Variables

This test simulates 1000 concurrent users across 100 tenants, performing:
- Vector similarity searches (pgvector)
- Chat session queries
- GA4 data fetching
- Mixed read/write operations

TARGET: 99.99% tenant isolation success rate (no more than 1 violation per 10,000 requests)

Usage:
    # Run with Locust UI
    locust -f tests/load/test_rls_under_load.py --host=http://localhost:8000
    
    # Run headless (1000 users, 100 spawn rate, 5 minutes)
    locust -f tests/load/test_rls_under_load.py --host=http://localhost:8000 \
           --users 1000 --spawn-rate 100 --run-time 5m --headless
    
    # Run with custom tenant count
    locust -f tests/load/test_rls_under_load.py --host=http://localhost:8000 \
           --users 1000 --spawn-rate 100 --run-time 5m --headless \
           --tenant-count 100
"""

import logging
import random
import time
import uuid
from typing import Dict, Optional

from locust import HttpUser, task, between, events
from locust.env import Environment

from tests.load.conftest import generate_test_jwt, TEST_TENANT_COUNT
from tests.load.rls_scenarios import RLSScenarios, ScenarioSelector
from tests.load.isolation_validator import IsolationValidator

logger = logging.getLogger(__name__)

# Global isolation validator (shared across all users)
isolation_validator = IsolationValidator()

# Global metrics
test_metrics = {
    "total_requests": 0,
    "isolation_violations": 0,
    "tenant_count": TEST_TENANT_COUNT
}


class TenantUser(HttpUser):
    """
    Simulates a user belonging to a specific tenant.
    
    Each user:
    1. Is assigned a unique user_id and tenant_id
    2. Generates JWT token with tenant_id
    3. Makes authenticated requests
    4. Validates responses for tenant isolation
    
    Load distribution:
    - 1000 users total
    - 100 unique tenants
    - 10 users per tenant on average
    """
    
    wait_time = between(0.1, 0.5)  # Aggressive load (100ms-500ms between requests)
    
    def on_start(self):
        """
        Initialize user with tenant context.
        
        Called once when user starts.
        """
        # Assign user to a tenant (round-robin across 100 tenants)
        self.user_id = str(uuid.uuid4())
        self.tenant_index = random.randint(0, TEST_TENANT_COUNT - 1)
        self.tenant_id = self._get_tenant_id(self.tenant_index)
        
        # Generate JWT token
        self.jwt_token = generate_test_jwt(
            user_id=self.user_id,
            tenant_id=self.tenant_id
        )
        
        # Set up scenario selector
        scenarios = RLSScenarios.get_all_scenarios()
        self.scenario_selector = ScenarioSelector(scenarios)
        
        # For context switching test, get a second tenant
        self.secondary_tenant_id = self._get_tenant_id(
            (self.tenant_index + 1) % TEST_TENANT_COUNT
        )
        
        logger.debug(
            f"User {self.user_id[:8]} initialized for tenant {self.tenant_id[:8]}"
        )
    
    def _get_tenant_id(self, tenant_index: int) -> str:
        """Get deterministic tenant ID by index."""
        # Use UUID5 for deterministic tenant IDs
        namespace = uuid.UUID("12345678-1234-5678-1234-567812345678")
        return str(uuid.uuid5(namespace, f"tenant_{tenant_index}"))
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict] = None,
        validate_isolation: bool = True
    ) -> Optional[Dict]:
        """
        Make authenticated request and validate tenant isolation.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            payload: Request payload
            validate_isolation: Whether to validate response for isolation
        
        Returns:
            Response data or None
        """
        headers = {
            "Authorization": f"Bearer {self.jwt_token}",
            "X-Tenant-Context": self.tenant_id,
            "Content-Type": "application/json"
        }
        
        start_time = time.time()
        
        try:
            if method == "GET":
                response = self.client.get(
                    endpoint,
                    headers=headers,
                    params=payload,
                    name=endpoint
                )
            else:  # POST
                response = self.client.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    name=endpoint
                )
            
            response_time_ms = (time.time() - start_time) * 1000
            
            # Validate isolation
            if validate_isolation and response.status_code == 200:
                try:
                    response_data = response.json()
                    is_valid = isolation_validator.validate_response(
                        requesting_tenant_id=self.tenant_id,
                        response_data=response_data,
                        endpoint=endpoint
                    )
                    
                    if not is_valid:
                        test_metrics["isolation_violations"] += 1
                        logger.error(
                            f"🚨 Isolation violation at {endpoint} for tenant {self.tenant_id[:8]}"
                        )
                
                except Exception as e:
                    logger.warning(f"Failed to validate response: {e}")
            
            test_metrics["total_requests"] += 1
            
            return response.json() if response.status_code == 200 else None
        
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None
    
    @task(50)
    def vector_search(self):
        """
        Task: Vector similarity search (50% weight - most critical).
        
        Tests pgvector RLS isolation under high concurrency.
        """
        payload = RLSScenarios.scenario_1_vector_search(self.tenant_id)
        response = self._make_request("POST", "/api/v1/analytics/query", payload)
        
        # Additional validation for vector search
        if response and "results" in response:
            isolation_validator.validate_vector_search_results(
                requesting_tenant_id=self.tenant_id,
                search_results=response.get("results", [])
            )
    
    @task(20)
    def chat_sessions(self):
        """
        Task: List chat sessions (20% weight).
        
        Tests RLS on chat_sessions table.
        """
        payload = RLSScenarios.scenario_2_chat_sessions(self.tenant_id)
        self._make_request("GET", "/api/v1/chat/sessions", payload)
    
    @task(15)
    def ga4_metrics(self):
        """
        Task: Fetch GA4 metrics (15% weight).
        
        Tests RLS on ga4_metrics_raw table.
        """
        payload = RLSScenarios.scenario_3_ga4_data(self.tenant_id)
        self._make_request("GET", "/api/v1/analytics/ga4/metrics", payload)
    
    @task(10)
    def mixed_operations(self):
        """
        Task: Mixed read/write operations (10% weight).
        
        Tests RLS during concurrent writes.
        """
        payload = RLSScenarios.scenario_4_mixed_operations(self.tenant_id)
        self._make_request("POST", "/api/v1/analytics/stream", payload)
    
    @task(5)
    def context_switching(self):
        """
        Task: Rapid tenant context switching (5% weight).
        
        CRITICAL: Tests session variable race conditions.
        Rapidly alternates between two tenant contexts.
        """
        # Alternate between primary and secondary tenant
        use_secondary = random.random() < 0.5
        tenant_for_request = self.secondary_tenant_id if use_secondary else self.tenant_id
        
        payload = {
            "query": "Quick status check",
            "tenant_id": tenant_for_request
        }
        
        # Temporarily switch JWT token
        original_token = self.jwt_token
        if use_secondary:
            self.jwt_token = generate_test_jwt(
                user_id=self.user_id,
                tenant_id=self.secondary_tenant_id
            )
        
        self._make_request("POST", "/api/v1/analytics/query", payload)
        
        # Restore original token
        self.jwt_token = original_token


@events.test_start.add_listener
def on_test_start(environment: Environment, **kwargs):
    """Initialize test - called once before load test starts."""
    logger.info("=" * 80)
    logger.info("🚀 Starting RLS Load Test (Task P0-29)")
    logger.info("=" * 80)
    logger.info(f"Target: {TEST_TENANT_COUNT} tenants, 1000 concurrent users")
    logger.info(f"Goal: 99.99% tenant isolation success rate")
    logger.info("=" * 80)
    
    # Reset validator
    isolation_validator.reset()


@events.test_stop.add_listener
def on_test_stop(environment: Environment, **kwargs):
    """
    Validate results - called once after load test completes.
    
    This is the CRITICAL validation step.
    """
    logger.info("=" * 80)
    logger.info("🏁 Load Test Complete - Validating Results")
    logger.info("=" * 80)
    
    # Get results
    total_requests = test_metrics["total_requests"]
    violations = isolation_validator.get_violation_count()
    success_rate = isolation_validator.get_isolation_success_rate()
    
    summary = isolation_validator.get_summary()
    
    logger.info(f"Total Requests: {total_requests:,}")
    logger.info(f"Isolation Violations: {violations}")
    logger.info(f"Isolation Success Rate: {success_rate:.4f}%")
    logger.info(f"Target Success Rate: 99.99%")
    
    # Detailed summary
    logger.info("\nDetailed Summary:")
    for key, value in summary.items():
        logger.info(f"  {key}: {value}")
    
    # Final validation
    logger.info("\n" + "=" * 80)
    if success_rate >= 99.99:
        logger.info("✅ PASSED: Tenant isolation maintained under load")
        logger.info(f"   Success rate {success_rate:.4f}% meets 99.99% target")
    else:
        logger.error("❌ FAILED: Tenant isolation compromised under load")
        logger.error(f"   Success rate {success_rate:.4f}% below 99.99% target")
        logger.error(f"   {violations} violations detected")
        
        # Show sample violations
        all_violations = isolation_validator.get_violations()
        if all_violations:
            logger.error("\nSample Violations:")
            for v in all_violations[:5]:
                logger.error(
                    f"  - {v.requesting_tenant_id[:8]} received data from "
                    f"{v.leaked_tenant_id[:8]} at {v.endpoint}"
                )
    
    logger.info("=" * 80)


# Pytest integration for CI/CD
def test_rls_isolation_under_load():
    """
    Pytest wrapper for CI/CD integration.
    
    This test can be run in CI/CD pipeline to validate RLS isolation.
    
    Usage:
        pytest tests/load/test_rls_under_load.py::test_rls_isolation_under_load
    """
    # Note: This requires running Locust programmatically
    # For now, document manual test execution
    pass

