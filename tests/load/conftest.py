"""
Load test fixtures and configuration.

Provides:
- JWT token generation for test tenants
- Database connection pools
- Test data seeding
- Metrics collectors
"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List
from jose import jwt

# Test configuration
LOCUST_HOST = "http://localhost:8000"
TEST_TENANT_COUNT = 100  # Number of unique tenants to simulate
CONCURRENT_USERS = 1000  # Target concurrent users

# JWT configuration (must match production settings)
SECRET_KEY = "test-secret-key-for-load-testing"
ALGORITHM = "HS256"


@pytest.fixture(scope="session")
def jwt_secret() -> str:
    """JWT secret key for test token generation."""
    return SECRET_KEY


@pytest.fixture(scope="session")
def test_tenants() -> List[Dict[str, str]]:
    """
    Generate test tenant data.
    
    Creates 100 unique tenant IDs for load testing.
    Each tenant will have 10 concurrent users (1000 total users).
    """
    tenants = []
    for i in range(TEST_TENANT_COUNT):
        tenant_id = str(uuid.uuid4())
        tenants.append({
            "tenant_id": tenant_id,
            "tenant_name": f"load_test_tenant_{i}",
            "ga4_property_id": f"properties/test-{i}"
        })
    return tenants


def generate_test_jwt(
    user_id: str,
    tenant_id: str,
    email: str = "loadtest@example.com",
    expires_delta: timedelta = timedelta(hours=1)
) -> str:
    """
    Generate JWT token for load testing.
    
    Args:
        user_id: User UUID
        tenant_id: Tenant UUID
        email: User email
        expires_delta: Token expiration time
    
    Returns:
        JWT token string
    """
    expire = datetime.utcnow() + expires_delta
    payload = {
        "sub": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@pytest.fixture(scope="session")
def token_generator():
    """Factory for generating JWT tokens."""
    return generate_test_jwt


@pytest.fixture(scope="session")
def test_embeddings() -> List[List[float]]:
    """
    Generate test embeddings for vector search.
    
    Creates 10 unique embedding vectors (1536 dimensions).
    Each tenant will have these same embeddings stored.
    """
    import numpy as np
    
    embeddings = []
    for i in range(10):
        # Generate random normalized vectors
        vec = np.random.randn(1536)
        vec = vec / np.linalg.norm(vec)
        embeddings.append(vec.tolist())
    
    return embeddings


@pytest.fixture(scope="session")
def isolation_validator():
    """
    Cross-tenant leak detection validator.
    
    Tracks all responses and validates no cross-tenant data leakage.
    """
    from tests.load.isolation_validator import IsolationValidator
    return IsolationValidator()


class LoadTestMetrics:
    """Metrics collector for load test results."""
    
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.isolation_violations = 0
        self.response_times = []
    
    def record_request(
        self,
        success: bool,
        response_time_ms: float,
        has_violation: bool = False
    ):
        """Record a request result."""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        if has_violation:
            self.isolation_violations += 1
        
        self.response_times.append(response_time_ms)
    
    def get_summary(self) -> Dict:
        """Get metrics summary."""
        if not self.response_times:
            return {
                "total_requests": 0,
                "success_rate": 0.0,
                "isolation_rate": 100.0,
                "p50_latency": 0,
                "p95_latency": 0,
                "p99_latency": 0
            }
        
        import numpy as np
        response_times = np.array(self.response_times)
        
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": (self.successful_requests / self.total_requests) * 100,
            "isolation_violations": self.isolation_violations,
            "isolation_rate": ((self.total_requests - self.isolation_violations) / self.total_requests) * 100,
            "p50_latency": np.percentile(response_times, 50),
            "p95_latency": np.percentile(response_times, 95),
            "p99_latency": np.percentile(response_times, 99),
            "avg_latency": np.mean(response_times),
            "max_latency": np.max(response_times)
        }


@pytest.fixture(scope="session")
def metrics_collector():
    """Global metrics collector for load tests."""
    return LoadTestMetrics()

