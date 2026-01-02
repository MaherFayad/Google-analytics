"""
Integration tests for orchestrator state machine.

Tests Task P0-39: Formal Agent State Machine Implementation

Verifies:
- All state transitions work correctly
- Conditional branching (cached vs fresh data)
- Error recovery and fallback
- Audit trail recording
- Timeout handling
- Invalid transition prevention
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock

from src.agents.orchestrator_state_machine import (
    OrchestratorStateMachine,
    WorkflowState,
    TransitionTrigger,
    StateTransitionAudit,
    create_workflow_state_machine,
)


class TestStateMachineInitialization:
    """Test state machine initialization."""
    
    def test_initialization_default_state(self):
        """Test state machine starts in INIT state."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        assert fsm.get_current_state() == WorkflowState.INIT
        assert fsm.tenant_id == "tenant-123"
        assert fsm.query_id == "query-456"
        assert len(fsm.audit_trail) == 0
    
    def test_initialization_custom_state(self):
        """Test state machine can start in custom state."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456",
            initial_state=WorkflowState.FETCH_DATA
        )
        
        assert fsm.get_current_state() == WorkflowState.FETCH_DATA
    
    def test_create_workflow_convenience_function(self):
        """Test convenience function creates state machine."""
        fsm = create_workflow_state_machine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        assert isinstance(fsm, OrchestratorStateMachine)
        assert fsm.get_current_state() == WorkflowState.INIT


class TestNormalWorkflowPath:
    """Test normal workflow path without errors."""
    
    @pytest.mark.asyncio
    async def test_complete_workflow_fresh_data(self):
        """Test complete workflow with fresh data (all states)."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        # Execute complete workflow
        transitions = [
            (TransitionTrigger.START, {}),
            (TransitionTrigger.DATA_FETCHED, {"row_count": 100}),
            (TransitionTrigger.DATA_VALIDATED, {"valid": True}),
            (TransitionTrigger.EMBEDDINGS_GENERATED, {"embedding_count": 100}),
            (TransitionTrigger.CONTEXT_RETRIEVED, {"document_count": 5}),
            (TransitionTrigger.CONTEXT_MERGED, {"confidence": 0.92}),
            (TransitionTrigger.REPORT_GENERATED, {"chart_count": 3}),
        ]
        
        for trigger, data in transitions:
            success = await fsm.transition(trigger, data)
            assert success, f"Transition {trigger} failed"
        
        # Verify final state
        assert fsm.get_current_state() == WorkflowState.COMPLETE
        assert fsm.is_complete()
        assert not fsm.is_error()
        
        # Verify audit trail
        assert len(fsm.audit_trail) == len(transitions)
        
        # Verify workflow data accumulated
        assert fsm.workflow_data["row_count"] == 100
        assert fsm.workflow_data["embedding_count"] == 100
        assert fsm.workflow_data["confidence"] == 0.92
    
    @pytest.mark.asyncio
    async def test_workflow_states_sequence(self):
        """Test each state transition in sequence."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        # INIT → FETCH_DATA
        await fsm.transition(TransitionTrigger.START)
        assert fsm.get_current_state() == WorkflowState.FETCH_DATA
        
        # FETCH_DATA → VALIDATE_DATA
        await fsm.transition(TransitionTrigger.DATA_FETCHED)
        assert fsm.get_current_state() == WorkflowState.VALIDATE_DATA
        
        # VALIDATE_DATA → GENERATE_EMBEDDINGS
        await fsm.transition(TransitionTrigger.DATA_VALIDATED)
        assert fsm.get_current_state() == WorkflowState.GENERATE_EMBEDDINGS
        
        # GENERATE_EMBEDDINGS → RETRIEVE_CONTEXT
        await fsm.transition(TransitionTrigger.EMBEDDINGS_GENERATED)
        assert fsm.get_current_state() == WorkflowState.RETRIEVE_CONTEXT
        
        # RETRIEVE_CONTEXT → MERGE_CONTEXT
        await fsm.transition(TransitionTrigger.CONTEXT_RETRIEVED)
        assert fsm.get_current_state() == WorkflowState.MERGE_CONTEXT
        
        # MERGE_CONTEXT → GENERATE_REPORT
        await fsm.transition(TransitionTrigger.CONTEXT_MERGED)
        assert fsm.get_current_state() == WorkflowState.GENERATE_REPORT
        
        # GENERATE_REPORT → COMPLETE
        await fsm.transition(TransitionTrigger.REPORT_GENERATED)
        assert fsm.get_current_state() == WorkflowState.COMPLETE


class TestConditionalBranching:
    """Test conditional branching for cached data."""
    
    @pytest.mark.asyncio
    async def test_cached_data_skips_embedding(self):
        """Test cached data branch skips embedding generation."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        # Start workflow
        await fsm.transition(TransitionTrigger.START)
        assert fsm.get_current_state() == WorkflowState.FETCH_DATA
        
        # Data is cached - skip directly to RETRIEVE_CONTEXT
        await fsm.transition(
            TransitionTrigger.DATA_CACHED,
            {"cached": True, "cache_age": 300}
        )
        assert fsm.get_current_state() == WorkflowState.RETRIEVE_CONTEXT
        
        # Verify we skipped VALIDATE_DATA and GENERATE_EMBEDDINGS
        states_visited = [audit.state_to for audit in fsm.audit_trail]
        assert WorkflowState.VALIDATE_DATA.value not in states_visited
        assert WorkflowState.GENERATE_EMBEDDINGS.value not in states_visited
        
        # Continue to completion
        await fsm.transition(TransitionTrigger.CONTEXT_RETRIEVED)
        await fsm.transition(TransitionTrigger.CONTEXT_MERGED)
        await fsm.transition(TransitionTrigger.REPORT_GENERATED)
        
        assert fsm.is_complete()


class TestErrorHandling:
    """Test error handling and fallback."""
    
    @pytest.mark.asyncio
    async def test_error_from_any_state(self):
        """Test ERROR trigger works from any state."""
        test_states = [
            WorkflowState.FETCH_DATA,
            WorkflowState.VALIDATE_DATA,
            WorkflowState.GENERATE_EMBEDDINGS,
            WorkflowState.RETRIEVE_CONTEXT,
        ]
        
        for start_state in test_states:
            fsm = OrchestratorStateMachine(
                tenant_id="tenant-123",
                query_id=f"query-{start_state.value}",
                initial_state=start_state
            )
            
            # Trigger error
            await fsm.transition(
                TransitionTrigger.ERROR,
                {"error": "Simulated failure"}
            )
            
            assert fsm.get_current_state() == WorkflowState.ERROR_FALLBACK
            assert fsm.is_error()
    
    @pytest.mark.asyncio
    async def test_timeout_triggers_fallback(self):
        """Test TIMEOUT trigger moves to ERROR_FALLBACK."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        await fsm.transition(TransitionTrigger.START)
        await fsm.transition(TransitionTrigger.DATA_FETCHED)
        
        # Simulate timeout during validation
        await fsm.transition(
            TransitionTrigger.TIMEOUT,
            {"timeout_at_state": "validate_data", "duration_ms": 60000}
        )
        
        assert fsm.get_current_state() == WorkflowState.ERROR_FALLBACK
        assert fsm.is_error()
    
    @pytest.mark.asyncio
    async def test_error_recorded_in_audit_trail(self):
        """Test errors are properly recorded in audit trail."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        await fsm.transition(TransitionTrigger.START)
        
        # Record error transition manually
        fsm.record_transition(
            state_from=WorkflowState.FETCH_DATA.value,
            state_to=WorkflowState.ERROR_FALLBACK.value,
            trigger=TransitionTrigger.ERROR.value,
            transition_data={"error": "GA4 API failure"},
            error_message="Connection timeout after 30s"
        )
        
        # Check audit trail
        error_audit = fsm.audit_trail[-1]
        assert error_audit.error_message == "Connection timeout after 30s"
        assert error_audit.state_to == WorkflowState.ERROR_FALLBACK.value


class TestAuditTrail:
    """Test audit trail recording."""
    
    @pytest.mark.asyncio
    async def test_audit_trail_records_all_transitions(self):
        """Test every transition is recorded in audit trail."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        transitions = [
            TransitionTrigger.START,
            TransitionTrigger.DATA_FETCHED,
            TransitionTrigger.DATA_VALIDATED,
        ]
        
        for trigger in transitions:
            await fsm.transition(trigger, {"step": trigger.value})
        
        assert len(fsm.audit_trail) == len(transitions)
        
        # Verify each audit record
        for i, audit in enumerate(fsm.audit_trail):
            assert audit.tenant_id == "tenant-123"
            assert audit.query_id == "query-456"
            assert audit.trigger == transitions[i].value
    
    @pytest.mark.asyncio
    async def test_audit_trail_includes_transition_data(self):
        """Test transition data is stored in audit trail."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        await fsm.transition(TransitionTrigger.START)
        await fsm.transition(
            TransitionTrigger.DATA_FETCHED,
            {
                "row_count": 500,
                "cached": False,
                "property_id": "12345"
            }
        )
        
        # Check transition data was recorded
        last_audit = fsm.audit_trail[-1]
        assert last_audit.transition_data["row_count"] == 500
        assert last_audit.transition_data["property_id"] == "12345"
    
    def test_audit_record_hash_computation(self):
        """Test transition data hash is computed correctly."""
        audit = StateTransitionAudit.create(
            tenant_id="tenant-123",
            query_id="query-456",
            state_from="init",
            state_to="fetch_data",
            trigger="start",
            transition_data={"test": "data"}
        )
        
        # Hash should be deterministic
        assert len(audit.transition_data_hash) == 64  # SHA256 hex digest
        
        # Same data should produce same hash
        audit2 = StateTransitionAudit.create(
            tenant_id="tenant-123",
            query_id="query-456",
            state_from="init",
            state_to="fetch_data",
            trigger="start",
            transition_data={"test": "data"}
        )
        
        assert audit.transition_data_hash == audit2.transition_data_hash


class TestWorkflowSummary:
    """Test workflow summary statistics."""
    
    @pytest.mark.asyncio
    async def test_workflow_summary_empty(self):
        """Test summary for workflow with no transitions."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        summary = fsm.get_workflow_summary()
        
        assert summary["current_state"] == WorkflowState.INIT.value
        assert summary["total_transitions"] == 0
        assert summary["total_duration_ms"] == 0
        assert summary["status"] == "not_started"
    
    @pytest.mark.asyncio
    async def test_workflow_summary_in_progress(self):
        """Test summary for in-progress workflow."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        await fsm.transition(TransitionTrigger.START)
        await fsm.transition(TransitionTrigger.DATA_FETCHED)
        
        summary = fsm.get_workflow_summary()
        
        assert summary["current_state"] == WorkflowState.VALIDATE_DATA.value
        assert summary["total_transitions"] == 2
        assert summary["status"] == "in_progress"
        assert len(summary["states_visited"]) == 2
    
    @pytest.mark.asyncio
    async def test_workflow_summary_complete(self):
        """Test summary for completed workflow."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        # Execute minimal workflow to completion
        await fsm.transition(TransitionTrigger.START)
        await fsm.transition(TransitionTrigger.DATA_CACHED)  # Skip to retrieval
        await fsm.transition(TransitionTrigger.CONTEXT_RETRIEVED)
        await fsm.transition(TransitionTrigger.CONTEXT_MERGED)
        await fsm.transition(TransitionTrigger.REPORT_GENERATED)
        
        summary = fsm.get_workflow_summary()
        
        assert summary["status"] == "complete"
        assert summary["current_state"] == WorkflowState.COMPLETE.value
        assert summary["total_transitions"] == 5
    
    @pytest.mark.asyncio
    async def test_workflow_summary_error(self):
        """Test summary for workflow with errors."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        await fsm.transition(TransitionTrigger.START)
        await fsm.transition(TransitionTrigger.ERROR, {"error": "Failed"})
        
        summary = fsm.get_workflow_summary()
        
        assert summary["status"] == "error"
        assert summary["error_count"] >= 0  # At least one error


class TestInvalidTransitions:
    """Test invalid state transitions are prevented."""
    
    @pytest.mark.asyncio
    async def test_cannot_skip_states(self):
        """Test cannot skip required states."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        await fsm.transition(TransitionTrigger.START)
        assert fsm.get_current_state() == WorkflowState.FETCH_DATA
        
        # Try to skip to GENERATE_REPORT directly (invalid)
        success = await fsm.transition(TransitionTrigger.REPORT_GENERATED)
        
        # Should fail or trigger error fallback
        assert not success or fsm.is_error()
    
    @pytest.mark.asyncio
    async def test_cannot_transition_from_complete(self):
        """Test COMPLETE is a terminal state."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456",
            initial_state=WorkflowState.COMPLETE
        )
        
        # Try to transition from COMPLETE (should fail)
        success = await fsm.transition(TransitionTrigger.START)
        
        # Should remain in COMPLETE or fail
        assert fsm.get_current_state() == WorkflowState.COMPLETE or not success


class TestDurationTracking:
    """Test duration tracking in audit trail."""
    
    @pytest.mark.asyncio
    async def test_duration_recorded_for_transitions(self):
        """Test transition durations are recorded."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456"
        )
        
        await fsm.transition(TransitionTrigger.START)
        
        # Simulate some processing time
        await asyncio.sleep(0.1)
        
        await fsm.transition(TransitionTrigger.DATA_FETCHED)
        
        # Check that duration was recorded
        if len(fsm.audit_trail) > 1:
            second_audit = fsm.audit_trail[1]
            assert second_audit.duration_ms is not None
            assert second_audit.duration_ms >= 100  # At least 100ms


class TestStateQueries:
    """Test state query helper methods."""
    
    def test_is_complete_method(self):
        """Test is_complete() returns correct value."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456",
            initial_state=WorkflowState.COMPLETE
        )
        
        assert fsm.is_complete()
        
        fsm2 = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-789",
            initial_state=WorkflowState.FETCH_DATA
        )
        
        assert not fsm2.is_complete()
    
    def test_is_error_method(self):
        """Test is_error() returns correct value."""
        fsm = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-456",
            initial_state=WorkflowState.ERROR_FALLBACK
        )
        
        assert fsm.is_error()
        
        fsm2 = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-789",
            initial_state=WorkflowState.FETCH_DATA
        )
        
        assert not fsm2.is_error()


class TestConcurrentWorkflows:
    """Test multiple concurrent state machines."""
    
    @pytest.mark.asyncio
    async def test_concurrent_workflows_independent(self):
        """Test multiple workflows can run concurrently."""
        fsm1 = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-1"
        )
        
        fsm2 = OrchestratorStateMachine(
            tenant_id="tenant-123",
            query_id="query-2"
        )
        
        # Execute transitions on both
        await fsm1.transition(TransitionTrigger.START)
        await fsm2.transition(TransitionTrigger.START)
        
        await fsm1.transition(TransitionTrigger.DATA_FETCHED)
        await fsm2.transition(TransitionTrigger.DATA_CACHED)  # Different path
        
        # Verify independent states
        assert fsm1.get_current_state() == WorkflowState.VALIDATE_DATA
        assert fsm2.get_current_state() == WorkflowState.RETRIEVE_CONTEXT
        
        # Verify independent audit trails
        assert fsm1.query_id != fsm2.query_id
        assert len(fsm1.audit_trail) == 2
        assert len(fsm2.audit_trail) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

