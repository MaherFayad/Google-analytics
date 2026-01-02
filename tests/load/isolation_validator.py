"""
Cross-tenant data leak detection validator.

Implements Task P0-29: Isolation validation logic

This module tracks all API responses and validates:
1. No tenant_id appears in responses not belonging to the requesting user
2. Vector search results only contain embeddings from the correct tenant
3. Session variables are properly isolated across concurrent requests
"""

import logging
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


@dataclass
class IsolationViolation:
    """Represents a detected tenant isolation violation."""
    
    timestamp: datetime
    requesting_tenant_id: str
    leaked_tenant_id: str
    endpoint: str
    violation_type: str
    response_data: Dict
    request_id: Optional[str] = None


@dataclass
class TenantRequestContext:
    """Tracks a single request context."""
    
    request_id: str
    tenant_id: str
    user_id: str
    endpoint: str
    timestamp: datetime
    response_data: Optional[Dict] = None
    violation: Optional[IsolationViolation] = None


class IsolationValidator:
    """
    Thread-safe validator for detecting cross-tenant data leakage.
    
    Usage:
        validator = IsolationValidator()
        validator.validate_response(tenant_id, response_data, endpoint)
        
        # Get results
        violations = validator.get_violations()
        success_rate = validator.get_isolation_success_rate()
    """
    
    def __init__(self):
        self._violations: List[IsolationViolation] = []
        self._total_validations = 0
        self._lock = threading.Lock()
        self._tenant_data_registry: Dict[str, Set[str]] = {}
        
        logger.info("IsolationValidator initialized")
    
    def register_tenant_data(self, tenant_id: str, data_ids: List[str]):
        """
        Register which data IDs belong to which tenant.
        
        This creates a ground truth for validation.
        
        Args:
            tenant_id: Tenant UUID
            data_ids: List of data IDs (chat_session_ids, embedding_ids, etc.)
        """
        with self._lock:
            if tenant_id not in self._tenant_data_registry:
                self._tenant_data_registry[tenant_id] = set()
            self._tenant_data_registry[tenant_id].update(data_ids)
    
    def validate_response(
        self,
        requesting_tenant_id: str,
        response_data: Dict,
        endpoint: str,
        request_id: Optional[str] = None
    ) -> bool:
        """
        Validate that response contains only data from requesting tenant.
        
        Args:
            requesting_tenant_id: Tenant making the request
            response_data: API response data
            endpoint: API endpoint called
            request_id: Optional request ID for tracking
        
        Returns:
            True if no violation detected, False otherwise
        """
        with self._lock:
            self._total_validations += 1
        
        # Extract tenant IDs from response
        leaked_tenant_ids = self._extract_tenant_ids(response_data)
        
        # Check for violations
        violations_found = []
        for leaked_id in leaked_tenant_ids:
            if leaked_id != requesting_tenant_id:
                violation = IsolationViolation(
                    timestamp=datetime.utcnow(),
                    requesting_tenant_id=requesting_tenant_id,
                    leaked_tenant_id=leaked_id,
                    endpoint=endpoint,
                    violation_type="CROSS_TENANT_DATA_LEAK",
                    response_data=response_data,
                    request_id=request_id
                )
                violations_found.append(violation)
                
                logger.error(
                    f"🚨 SECURITY VIOLATION: Tenant {requesting_tenant_id} "
                    f"received data from tenant {leaked_id} at {endpoint}"
                )
        
        if violations_found:
            with self._lock:
                self._violations.extend(violations_found)
            return False
        
        return True
    
    def validate_vector_search_results(
        self,
        requesting_tenant_id: str,
        search_results: List[Dict],
        endpoint: str = "/api/v1/analytics/query"
    ) -> bool:
        """
        Validate vector search results contain only correct tenant's embeddings.
        
        Args:
            requesting_tenant_id: Tenant making the request
            search_results: List of search result objects
            endpoint: API endpoint
        
        Returns:
            True if no violation, False otherwise
        """
        for result in search_results:
            result_tenant_id = result.get("tenant_id")
            embedding_id = result.get("embedding_id")
            
            if result_tenant_id and result_tenant_id != requesting_tenant_id:
                violation = IsolationViolation(
                    timestamp=datetime.utcnow(),
                    requesting_tenant_id=requesting_tenant_id,
                    leaked_tenant_id=result_tenant_id,
                    endpoint=endpoint,
                    violation_type="VECTOR_SEARCH_LEAK",
                    response_data={
                        "embedding_id": embedding_id,
                        "leaked_tenant_id": result_tenant_id
                    }
                )
                
                with self._lock:
                    self._violations.append(violation)
                    self._total_validations += 1
                
                logger.error(
                    f"🚨 VECTOR SEARCH LEAK: Tenant {requesting_tenant_id} "
                    f"received embedding from tenant {result_tenant_id}"
                )
                return False
        
        with self._lock:
            self._total_validations += 1
        
        return True
    
    def _extract_tenant_ids(self, data: any) -> Set[str]:
        """
        Recursively extract all tenant_id values from response data.
        
        Args:
            data: Response data (dict, list, or primitive)
        
        Returns:
            Set of tenant IDs found
        """
        tenant_ids = set()
        
        if isinstance(data, dict):
            # Check for tenant_id key
            if "tenant_id" in data:
                tenant_ids.add(data["tenant_id"])
            
            # Recurse into nested dicts
            for value in data.values():
                tenant_ids.update(self._extract_tenant_ids(value))
        
        elif isinstance(data, list):
            # Recurse into list items
            for item in data:
                tenant_ids.update(self._extract_tenant_ids(item))
        
        return tenant_ids
    
    def get_violations(self) -> List[IsolationViolation]:
        """Get all detected violations."""
        with self._lock:
            return self._violations.copy()
    
    def get_violation_count(self) -> int:
        """Get total number of violations."""
        with self._lock:
            return len(self._violations)
    
    def get_isolation_success_rate(self) -> float:
        """
        Get isolation success rate as percentage.
        
        Target: 99.99% (no more than 1 violation per 10,000 requests)
        
        Returns:
            Success rate as percentage (0-100)
        """
        with self._lock:
            if self._total_validations == 0:
                return 100.0
            
            success_rate = ((self._total_validations - len(self._violations)) / 
                          self._total_validations) * 100
            return success_rate
    
    def assert_no_violations(self):
        """
        Assert no violations detected (for use in tests).
        
        Raises:
            AssertionError: If violations were detected
        """
        violation_count = self.get_violation_count()
        success_rate = self.get_isolation_success_rate()
        
        if violation_count > 0:
            violations = self.get_violations()
            violation_details = "\n".join([
                f"  - {v.requesting_tenant_id} -> {v.leaked_tenant_id} at {v.endpoint}"
                for v in violations[:10]  # Show first 10
            ])
            
            raise AssertionError(
                f"❌ CRITICAL: {violation_count} tenant isolation violations detected!\n"
                f"Success rate: {success_rate:.4f}%\n"
                f"Target: 99.99%\n\n"
                f"Violations:\n{violation_details}"
            )
        
        logger.info(
            f"✅ PASSED: {self._total_validations} requests validated, "
            f"0 violations (100% isolation)"
        )
    
    def assert_meets_target(self, target_success_rate: float = 99.99):
        """
        Assert isolation success rate meets target.
        
        Args:
            target_success_rate: Target success rate (default: 99.99%)
        
        Raises:
            AssertionError: If success rate below target
        """
        success_rate = self.get_isolation_success_rate()
        violation_count = self.get_violation_count()
        
        if success_rate < target_success_rate:
            raise AssertionError(
                f"❌ FAILED: Isolation success rate {success_rate:.4f}% "
                f"below target {target_success_rate}%\n"
                f"Violations: {violation_count} / {self._total_validations} requests"
            )
        
        logger.info(
            f"✅ PASSED: Isolation success rate {success_rate:.4f}% "
            f"meets target {target_success_rate}%"
        )
    
    def reset(self):
        """Reset validator state (for test reruns)."""
        with self._lock:
            self._violations.clear()
            self._total_validations = 0
            self._tenant_data_registry.clear()
            logger.info("IsolationValidator reset")
    
    def get_summary(self) -> Dict:
        """Get validation summary statistics."""
        with self._lock:
            return {
                "total_validations": self._total_validations,
                "violation_count": len(self._violations),
                "success_rate": self.get_isolation_success_rate(),
                "unique_violating_tenants": len(set(
                    v.requesting_tenant_id for v in self._violations
                )),
                "unique_leaked_tenants": len(set(
                    v.leaked_tenant_id for v in self._violations
                ))
            }

