"""
Integration tests for Orchestrator State Machine.

Tests Task P0-23: Agent Orchestration State Machine Implementation
"""

import pytest
import asyncio
from datetime import datetime
from uuid import uuid4

from agents.orchestrator_state_machine import (
    OrchestratorStateMachine,
    WorkflowState,
    TransitionTrigger,
    StateTransitionAudit,
)


@pytest.fixture
def tenant_id():
    """Generate tenant ID for tests."""
    return str(uuid4())


@pytest.fixture
def query_id():
    """Generate query ID for tests."""
    return str(uuid4())


@pytest.fixture
def state_machine(tenant_id, query_id):
    """Create state machine instance."""
    return OrchestratorStateMachine(
        tenant_id=tenant_id,
        query_id=query_id
    )


class TestStateMachineTransitions:
    """Test state machine transitions."""
    
    def test_initial_state(self, state_machine):
        """Test state machine starts in INIT state."""
        assert state_machine.current_state == WorkflowState.INIT
        assert state_machine.tenant_id is not None
        assert state_machine.query_id is not None
    
    @pytest.mark.asyncio
    async def test_happy_path_fresh_data(self, state_machine):
        """Test happy path with fresh data (full pipeline)."""
        # INIT → FETCH_DATA
        await state_machine.trigger(TransitionTrigger.START)
        assert state_machine.current_state == WorkflowState.FETCH_DATA
        
        # FETCH_DATA → VALIDATE_DATA
        await state_machine.trigger(TransitionTrigger.DATA_FETCHED)
        assert state_machine.current_state == WorkflowState.VALIDATE_DATA
        
        # VALIDATE_DATA → GENERATE_EMBEDDINGS
        await state_machine.trigger(TransitionTrigger.DATA_VALIDATED)
        assert state_machine.current_state == WorkflowState.GENERATE_EMBEDDINGS
        
        # GENERATE_EMBEDDINGS → RETRIEVE_CONTEXT
        await state_machine.trigger(TransitionTrigger.EMBEDDINGS_GENERATED)
        assert state_machine.current_state == WorkflowState.RETRIEVE_CONTEXT
        
        # RETRIEVE_CONTEXT → MERGE_CONTEXT
        await state_machine.trigger(TransitionTrigger.CONTEXT_RETRIEVED)
        assert state_machine.current_state == WorkflowState.MERGE_CONTEXT
        
        # MERGE_CONTEXT → GENERATE_REPORT
        await state_machine.trigger(TransitionTrigger.CONTEXT_MERGED)
        assert state_machine.current_state == WorkflowState.GENERATE_REPORT
        
        # GENERATE_REPORT → COMPLETE
        await state_machine.trigger(TransitionTrigger.REPORT_GENERATED)
        assert state_machine.current_state == WorkflowState.COMPLETE
    
    @pytest.mark.asyncio
    async def test_cached_data_path(self, state_machine):
        """Test cached data path (skip embedding generation)."""
        # INIT → FETCH_DATA
        await state_machine.trigger(TransitionTrigger.START)
        
        # FETCH_DATA → RETRIEVE_CONTEXT (cached data)
        await state_machine.trigger(TransitionTrigger.DATA_CACHED)
        assert state_machine.current_state == WorkflowState.RETRIEVE_CONTEXT
        
        # Continue to completion
        await state_machine.trigger(TransitionTrigger.CONTEXT_RETRIEVED)
        await state_machine.trigger(TransitionTrigger.CONTEXT_MERGED)
        await state_machine.trigger(TransitionTrigger.REPORT_GENERATED)
        assert state_machine.current_state == WorkflowState.COMPLETE
    
    @pytest.mark.asyncio
    async def test_error_transition(self, state_machine):
        """Test error transition from any state."""
        # Start workflow
        await state_machine.trigger(TransitionTrigger.START)
        await state_machine.trigger(TransitionTrigger.DATA_FETCHED)
        
        # Trigger error
        await state_machine.trigger(TransitionTrigger.ERROR)
        assert state_machine.current_state == WorkflowState.ERROR_FALLBACK
    
    @pytest.mark.asyncio
    async def test_timeout_transition(self, state_machine):
        """Test timeout transition."""
        await state_machine.trigger(TransitionTrigger.START)
        
        # Simulate timeout in FETCH_DATA state
        await state_machine.trigger(TransitionTrigger.TIMEOUT)
        assert state_machine.current_state == WorkflowState.ERROR_FALLBACK
    
    def test_invalid_transition_blocked(self, state_machine):
        """Test that invalid transitions are blocked."""
        # Try to skip from INIT to GENERATE_EMBEDDINGS
        with pytest.raises(Exception):  # Should raise transition error
            state_machine.trigger_sync(TransitionTrigger.EMBEDDINGS_GENERATED)
        
        # State should remain INIT
        assert state_machine.current_state == WorkflowState.INIT


class TestStateTransitionAudit:
    """Test state transition audit logging."""
    
    def test_audit_record_creation(self):
        """Test audit record is created with hash."""
        audit = StateTransitionAudit.create(
            tenant_id="tenant-123",
            query_id="query-456",
            state_from=WorkflowState.INIT.value,
            state_to=WorkflowState.FETCH_DATA.value,
            trigger=TransitionTrigger.START.value,
            transition_data={"cached": False},
            duration_ms=150
        )
        
        assert audit.tenant_id == "tenant-123"
        assert audit.query_id == "query-456"
        assert audit.state_from == WorkflowState.INIT.value
        assert audit.state_to == WorkflowState.FETCH_DATA.value
        assert audit.transition_data_hash is not None
        assert len(audit.transition_data_hash) == 64  # SHA256 hex
    
    def test_audit_hash_consistency(self):
        """Test same data produces same hash."""
        transition_data = {"cached": False, "property_id": "123"}
        
        audit1 = StateTransitionAudit.create(
            tenant_id="tenant-123",
            query_id="query-456",
            state_from=WorkflowState.INIT.value,
            state_to=WorkflowState.FETCH_DATA.value,
            trigger=TransitionTrigger.START.value,
            transition_data=transition_data
        )
        
        audit2 = StateTransitionAudit.create(
            tenant_id="tenant-123",
            query_id="query-456",
            state_from=WorkflowState.INIT.value,
            state_to=WorkflowState.FETCH_DATA.value,
            trigger=TransitionTrigger.START.value,
            transition_data=transition_data
        )
        
        # Same data should produce same hash
        assert audit1.transition_data_hash == audit2.transition_data_hash
    
    @pytest.mark.asyncio
    async def test_audit_trail_created(self, state_machine):
        """Test audit trail is created during transitions."""
        # Execute several transitions
        await state_machine.trigger(TransitionTrigger.START)
        await state_machine.trigger(TransitionTrigger.DATA_FETCHED)
        await state_machine.trigger(TransitionTrigger.DATA_VALIDATED)
        
        # Check audit trail
        audit_trail = state_machine.get_audit_trail()
        assert len(audit_trail) == 3
        
        # Verify first transition
        assert audit_trail[0].state_from == WorkflowState.INIT.value
        assert audit_trail[0].state_to == WorkflowState.FETCH_DATA.value
        
        # Verify last transition
        assert audit_trail[-1].state_to == WorkflowState.GENERATE_EMBEDDINGS.value


class TestConditionalBranching:
    """Test conditional state transitions."""
    
    @pytest.mark.asyncio
    async def test_fresh_data_branch(self, state_machine):
        """Test fresh data triggers embedding generation."""
        await state_machine.trigger(TransitionTrigger.START)
        
        # Fresh data should go to validation
        await state_machine.trigger(
            TransitionTrigger.DATA_FETCHED,
            transition_data={"cached": False}
        )
        assert state_machine.current_state == WorkflowState.VALIDATE_DATA
        
        # Then to embedding generation
        await state_machine.trigger(TransitionTrigger.DATA_VALIDATED)
        assert state_machine.current_state == WorkflowState.GENERATE_EMBEDDINGS
    
    @pytest.mark.asyncio
    async def test_cached_data_branch(self, state_machine):
        """Test cached data skips embedding generation."""
        await state_machine.trigger(TransitionTrigger.START)
        
        # Cached data should skip directly to retrieval
        await state_machine.trigger(
            TransitionTrigger.DATA_CACHED,
            transition_data={"cached": True, "cache_age_seconds": 300}
        )
        assert state_machine.current_state == WorkflowState.RETRIEVE_CONTEXT


class TestErrorRecovery:
    """Test error handling and recovery."""
    
    @pytest.mark.asyncio
    async def test_error_fallback_state(self, state_machine):
        """Test error transitions to fallback state."""
        await state_machine.trigger(TransitionTrigger.START)
        await state_machine.trigger(TransitionTrigger.DATA_FETCHED)
        
        # Trigger error
        await state_machine.trigger(
            TransitionTrigger.ERROR,
            transition_data={"error": "GA4 API timeout"}
        )
        
        assert state_machine.current_state == WorkflowState.ERROR_FALLBACK
        
        # Verify error is in audit trail
        audit_trail = state_machine.get_audit_trail()
        error_audit = [a for a in audit_trail if a.state_to == WorkflowState.ERROR_FALLBACK.value][0]
        assert error_audit is not None
        assert "error" in error_audit.transition_data
    
    @pytest.mark.asyncio
    async def test_error_from_multiple_states(self, state_machine):
        """Test error can be triggered from any state."""
        states_to_test = [
            (TransitionTrigger.START, WorkflowState.FETCH_DATA),
            (TransitionTrigger.DATA_FETCHED, WorkflowState.VALIDATE_DATA),
            (TransitionTrigger.DATA_VALIDATED, WorkflowState.GENERATE_EMBEDDINGS),
        ]
        
        for trigger, expected_state in states_to_test:
            # Reset state machine
            sm = OrchestratorStateMachine(
                tenant_id=str(uuid4()),
                query_id=str(uuid4())
            )
            
            # Get to specific state
            await sm.trigger(TransitionTrigger.START)
            if trigger != TransitionTrigger.START:
                await sm.trigger(trigger)
            
            # Trigger error from this state
            await sm.trigger(TransitionTrigger.ERROR)
            assert sm.current_state == WorkflowState.ERROR_FALLBACK


class TestConcurrentStateMachines:
    """Test multiple state machines can run concurrently."""
    
    @pytest.mark.asyncio
    async def test_concurrent_workflows(self, tenant_id):
        """Test multiple workflows can execute in parallel."""
        # Create 3 state machines for different queries
        sm1 = OrchestratorStateMachine(tenant_id=tenant_id, query_id=str(uuid4()))
        sm2 = OrchestratorStateMachine(tenant_id=tenant_id, query_id=str(uuid4()))
        sm3 = OrchestratorStateMachine(tenant_id=tenant_id, query_id=str(uuid4()))
        
        # Execute them concurrently
        async def run_workflow(sm):
            await sm.trigger(TransitionTrigger.START)
            await sm.trigger(TransitionTrigger.DATA_FETCHED)
            await sm.trigger(TransitionTrigger.DATA_VALIDATED)
            return sm.current_state
        
        results = await asyncio.gather(
            run_workflow(sm1),
            run_workflow(sm2),
            run_workflow(sm3)
        )
        
        # All should reach GENERATE_EMBEDDINGS state
        assert all(state == WorkflowState.GENERATE_EMBEDDINGS for state in results)
        
        # Each should have independent audit trail
        assert len(sm1.get_audit_trail()) == 3
        assert len(sm2.get_audit_trail()) == 3
        assert len(sm3.get_audit_trail()) == 3


class TestPerformanceMetrics:
    """Test state machine tracks performance metrics."""
    
    @pytest.mark.asyncio
    async def test_transition_duration_tracking(self, state_machine):
        """Test transition durations are tracked."""
        await state_machine.trigger(TransitionTrigger.START)
        await asyncio.sleep(0.1)  # Simulate some work
        await state_machine.trigger(TransitionTrigger.DATA_FETCHED)
        
        audit_trail = state_machine.get_audit_trail()
        
        # Check duration is tracked
        for audit in audit_trail:
            assert audit.duration_ms is not None or audit.duration_ms == 0
    
    def test_state_machine_metrics(self, state_machine):
        """Test state machine exposes metrics."""
        metrics = state_machine.get_metrics()
        
        assert "current_state" in metrics
        assert "total_transitions" in metrics
        assert "total_duration_ms" in metrics
        assert "error_count" in metrics

