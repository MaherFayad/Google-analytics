"""
RLS load test scenarios.

Implements Task P0-29: Test scenarios for RLS under load

Defines 5 comprehensive test scenarios:
1. Concurrent Vector Search (highest priority)
2. Concurrent Chat Session Queries
3. Concurrent GA4 Data Fetching
4. Mixed Read/Write Operations
5. Tenant Context Switching Stress Test
"""

from dataclasses import dataclass
from typing import Dict, List, Callable
import random


@dataclass
class LoadTestScenario:
    """Defines a load test scenario."""
    
    name: str
    description: str
    weight: int  # Probability weight (higher = more frequent)
    endpoint: str
    method: str
    generate_payload: Callable
    expected_status: int = 200


class RLSScenarios:
    """
    RLS load test scenario definitions.
    
    Each scenario tests different aspects of tenant isolation under load.
    """
    
    @staticmethod
    def scenario_1_vector_search(tenant_id: str) -> Dict:
        """
        Scenario 1: Concurrent Vector Search
        
        CRITICAL: Most important test - validates pgvector RLS isolation.
        
        Test:
        - 1000 concurrent users perform vector similarity search
        - Each user belongs to different tenant
        - Query: "Show me top marketing campaigns"
        - Validates: Results only contain tenant's own embeddings
        
        Args:
            tenant_id: Tenant UUID
        
        Returns:
            Request payload
        """
        queries = [
            "Show me top marketing campaigns",
            "What are the best performing pages?",
            "Compare mobile vs desktop traffic",
            "Show user engagement metrics",
            "What's my conversion rate trend?"
        ]
        
        return {
            "query": random.choice(queries),
            "tenant_id": tenant_id,
            "max_results": 10,
            "include_embeddings": False
        }
    
    @staticmethod
    def scenario_2_chat_sessions(tenant_id: str) -> Dict:
        """
        Scenario 2: Concurrent Chat Session Queries
        
        Test:
        - Users query their chat session history
        - Validates: No cross-tenant session leakage
        
        Args:
            tenant_id: Tenant UUID
        
        Returns:
            Request payload
        """
        return {
            "tenant_id": tenant_id,
            "limit": 50,
            "offset": 0
        }
    
    @staticmethod
    def scenario_3_ga4_data(tenant_id: str) -> Dict:
        """
        Scenario 3: Concurrent GA4 Data Fetching
        
        Test:
        - Multiple tenants fetch GA4 analytics data simultaneously
        - Validates: RLS filters apply to ga4_metrics_raw table
        
        Args:
            tenant_id: Tenant UUID
        
        Returns:
            Request payload
        """
        date_ranges = [
            {"start_date": "7daysAgo", "end_date": "today"},
            {"start_date": "30daysAgo", "end_date": "today"},
            {"start_date": "90daysAgo", "end_date": "today"}
        ]
        
        metrics = [
            ["sessions", "pageviews"],
            ["users", "sessions", "bounceRate"],
            ["conversions", "revenue"]
        ]
        
        return {
            "tenant_id": tenant_id,
            "date_range": random.choice(date_ranges),
            "metrics": random.choice(metrics)
        }
    
    @staticmethod
    def scenario_4_mixed_operations(tenant_id: str) -> Dict:
        """
        Scenario 4: Mixed Read/Write Operations
        
        Test:
        - Concurrent reads and writes to test RLS under mixed load
        - Create new chat message while querying embeddings
        - Validates: Session variables remain isolated during writes
        
        Args:
            tenant_id: Tenant UUID
        
        Returns:
            Request payload
        """
        return {
            "tenant_id": tenant_id,
            "query": "Create performance report",
            "stream": True  # SSE streaming
        }
    
    @staticmethod
    def scenario_5_context_switching(tenant_id_primary: str, tenant_id_secondary: str) -> Dict:
        """
        Scenario 5: Tenant Context Switching Stress Test
        
        CRITICAL: Tests session variable race conditions.
        
        Test:
        - Rapidly switch between two tenant contexts
        - Validates: No session variable bleed between requests
        
        Args:
            tenant_id_primary: First tenant UUID
            tenant_id_secondary: Second tenant UUID
        
        Returns:
            Request payload with alternating tenant
        """
        return {
            "tenant_id": random.choice([tenant_id_primary, tenant_id_secondary]),
            "query": "Quick status check"
        }
    
    @staticmethod
    def get_all_scenarios() -> List[LoadTestScenario]:
        """
        Get all test scenarios with weights.
        
        Weights determine frequency:
        - Vector search: 50% of requests (most critical)
        - Chat sessions: 20%
        - GA4 data: 15%
        - Mixed ops: 10%
        - Context switching: 5%
        
        Returns:
            List of LoadTestScenario objects
        """
        return [
            LoadTestScenario(
                name="vector_search",
                description="Concurrent vector similarity search",
                weight=50,
                endpoint="/api/v1/analytics/query",
                method="POST",
                generate_payload=RLSScenarios.scenario_1_vector_search
            ),
            LoadTestScenario(
                name="chat_sessions",
                description="List user chat sessions",
                weight=20,
                endpoint="/api/v1/chat/sessions",
                method="GET",
                generate_payload=RLSScenarios.scenario_2_chat_sessions
            ),
            LoadTestScenario(
                name="ga4_data",
                description="Fetch GA4 analytics data",
                weight=15,
                endpoint="/api/v1/analytics/ga4/metrics",
                method="GET",
                generate_payload=RLSScenarios.scenario_3_ga4_data
            ),
            LoadTestScenario(
                name="mixed_operations",
                description="Mixed read/write with streaming",
                weight=10,
                endpoint="/api/v1/analytics/stream",
                method="POST",
                generate_payload=RLSScenarios.scenario_4_mixed_operations
            ),
            LoadTestScenario(
                name="context_switching",
                description="Rapid tenant context switching",
                weight=5,
                endpoint="/api/v1/analytics/query",
                method="POST",
                generate_payload=RLSScenarios.scenario_5_context_switching
            )
        ]


class ScenarioSelector:
    """Weighted random scenario selector."""
    
    def __init__(self, scenarios: List[LoadTestScenario]):
        self.scenarios = scenarios
        self.weights = [s.weight for s in scenarios]
        self.total_weight = sum(self.weights)
    
    def select(self) -> LoadTestScenario:
        """Select a scenario based on weights."""
        return random.choices(self.scenarios, weights=self.weights, k=1)[0]

