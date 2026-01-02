"""
Formal Finite State Machine for Agent Orchestration.

Implements Task P0-39: Formal Agent State Machine Implementation

Provides:
- Deterministic state transitions for agent workflow
- Full audit trail of state changes
- Conditional branching (cached vs fresh data)
- Error recovery with fallback states
- Timeout detection and handling

Uses Python `transitions` library for robust FSM implementation.
"""

import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, List
from enum import Enum
import hashlib
import json

from transitions import Machine
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WorkflowState(str, Enum):
    """States in the agent orchestration workflow."""
    INIT = "init"
    FETCH_DATA = "fetch_data"
    VALIDATE_DATA = "validate_data"
    GENERATE_EMBEDDINGS = "generate_embeddings"
    RETRIEVE_CONTEXT = "retrieve_context"
    MERGE_CONTEXT = "merge_context"
    GENERATE_REPORT = "generate_report"
    COMPLETE = "complete"
    ERROR_FALLBACK = "error_fallback"


class TransitionTrigger(str, Enum):
    """Triggers that cause state transitions."""
    START = "start"
    DATA_FETCHED = "data_fetched"
    DATA_CACHED = "data_cached"
    DATA_VALIDATED = "data_validated"
    EMBEDDINGS_GENERATED = "embeddings_generated"
    CONTEXT_RETRIEVED = "context_retrieved"
    CONTEXT_MERGED = "context_merged"
    REPORT_GENERATED = "report_generated"
    ERROR = "error"
    TIMEOUT = "timeout"


class StateTransitionAudit(BaseModel):
    """Audit record for state transitions."""
    
    tenant_id: str
    query_id: str
    state_from: str
    state_to: str
    trigger: str
    transition_data: Dict[str, Any] = Field(default_factory=dict)
    transition_data_hash: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    
    @classmethod
    def create(
        cls,
        tenant_id: str,
        query_id: str,
        state_from: str,
        state_to: str,
        trigger: str,
        transition_data: Dict[str, Any],
        duration_ms: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> "StateTransitionAudit":
        """Create audit record with computed hash."""
        # Compute hash of transition data
        data_json = json.dumps(transition_data, sort_keys=True)
        data_hash = hashlib.sha256(data_json.encode()).hexdigest()
        
        return cls(
            tenant_id=tenant_id,
            query_id=query_id,
            state_from=state_from,
            state_to=state_to,
            trigger=trigger,
            transition_data=transition_data,
            transition_data_hash=data_hash,
            duration_ms=duration_ms,
            error_message=error_message
        )


class OrchestratorStateMachine:
    """
    Formal finite state machine for agent orchestration.
    
    Implements Task P0-39: Formal Agent State Machine Implementation
    
    States:
        INIT → FETCH_DATA → VALIDATE_DATA → GENERATE_EMBEDDINGS → 
        RETRIEVE_CONTEXT → MERGE_CONTEXT → GENERATE_REPORT → COMPLETE
    
    Conditional Branches:
        - FETCH_DATA → RETRIEVE_CONTEXT (if cached data, skip embedding)
        - Any State → ERROR_FALLBACK (on error or timeout)
    
    Features:
        - Full audit trail of transitions
        - Timeout detection
        - Error recovery
        - Conditional branching based on data state
    """
    
    # Define valid state transitions
    TRANSITIONS = [
        # Normal workflow path
        {
            'trigger': TransitionTrigger.START,
            'source': WorkflowState.INIT,
            'dest': WorkflowState.FETCH_DATA
        },
        {
            'trigger': TransitionTrigger.DATA_FETCHED,
            'source': WorkflowState.FETCH_DATA,
            'dest': WorkflowState.VALIDATE_DATA
        },
        {
            'trigger': TransitionTrigger.DATA_VALIDATED,
            'source': WorkflowState.VALIDATE_DATA,
            'dest': WorkflowState.GENERATE_EMBEDDINGS
        },
        {
            'trigger': TransitionTrigger.EMBEDDINGS_GENERATED,
            'source': WorkflowState.GENERATE_EMBEDDINGS,
            'dest': WorkflowState.RETRIEVE_CONTEXT
        },
        {
            'trigger': TransitionTrigger.CONTEXT_RETRIEVED,
            'source': WorkflowState.RETRIEVE_CONTEXT,
            'dest': WorkflowState.MERGE_CONTEXT
        },
        {
            'trigger': TransitionTrigger.CONTEXT_MERGED,
            'source': WorkflowState.MERGE_CONTEXT,
            'dest': WorkflowState.GENERATE_REPORT
        },
        {
            'trigger': TransitionTrigger.REPORT_GENERATED,
            'source': WorkflowState.GENERATE_REPORT,
            'dest': WorkflowState.COMPLETE
        },
        
        # Conditional branch: cached data skips embedding
        {
            'trigger': TransitionTrigger.DATA_CACHED,
            'source': WorkflowState.FETCH_DATA,
            'dest': WorkflowState.RETRIEVE_CONTEXT
        },
        
        # Error fallback from any state
        {
            'trigger': TransitionTrigger.ERROR,
            'source': '*',  # From any state
            'dest': WorkflowState.ERROR_FALLBACK
        },
        {
            'trigger': TransitionTrigger.TIMEOUT,
            'source': '*',
            'dest': WorkflowState.ERROR_FALLBACK
        },
    ]
    
    def __init__(
        self,
        tenant_id: str,
        query_id: str,
        initial_state: WorkflowState = WorkflowState.INIT
    ):
        """
        Initialize state machine.
        
        Args:
            tenant_id: Tenant ID for audit trail
            query_id: Query ID for audit trail
            initial_state: Starting state (default: INIT)
        """
        self.tenant_id = tenant_id
        self.query_id = query_id
        self.audit_trail: List[StateTransitionAudit] = []
        self.transition_start_time: Optional[float] = None
        self.workflow_data: Dict[str, Any] = {}
        
        # Create state machine
        self.machine = Machine(
            model=self,
            states=[state.value for state in WorkflowState],
            transitions=self.TRANSITIONS,
            initial=initial_state.value,
            auto_transitions=False,  # Only allow defined transitions
            after_state_change=self._on_state_change
        )
        
        logger.info(
            f"State machine initialized for query {query_id} "
            f"(tenant: {tenant_id}, initial: {initial_state.value})"
        )
    
    def _on_state_change(self):
        """Callback after state change - record audit trail."""
        # This is called by transitions library after state change
        pass
    
    def record_transition(
        self,
        state_from: str,
        state_to: str,
        trigger: str,
        transition_data: Dict[str, Any],
        error_message: Optional[str] = None
    ):
        """
        Record state transition in audit trail.
        
        Args:
            state_from: Source state
            state_to: Destination state
            trigger: Trigger that caused transition
            transition_data: Data associated with transition
            error_message: Error message if transition failed
        """
        # Calculate duration if we have start time
        duration_ms = None
        if self.transition_start_time:
            duration_ms = int((asyncio.get_event_loop().time() - self.transition_start_time) * 1000)
        
        # Create audit record
        audit = StateTransitionAudit.create(
            tenant_id=self.tenant_id,
            query_id=self.query_id,
            state_from=state_from,
            state_to=state_to,
            trigger=trigger,
            transition_data=transition_data,
            duration_ms=duration_ms,
            error_message=error_message
        )
        
        self.audit_trail.append(audit)
        
        logger.info(
            f"State transition: {state_from} → {state_to} "
            f"(trigger: {trigger}, duration: {duration_ms}ms)"
        )
        
        # Reset transition timer
        self.transition_start_time = asyncio.get_event_loop().time()
    
    async def transition(
        self,
        trigger: TransitionTrigger,
        transition_data: Dict[str, Any] = None
    ) -> bool:
        """
        Attempt state transition.
        
        Args:
            trigger: Trigger to fire
            transition_data: Data associated with transition
        
        Returns:
            True if transition succeeded, False otherwise
        """
        if transition_data is None:
            transition_data = {}
        
        current_state = self.state
        
        try:
            # Fire trigger (uses transitions library)
            trigger_method = getattr(self, trigger.value)
            trigger_method()
            
            # Record successful transition
            self.record_transition(
                state_from=current_state,
                state_to=self.state,
                trigger=trigger.value,
                transition_data=transition_data
            )
            
            # Store transition data
            self.workflow_data.update(transition_data)
            
            return True
        
        except Exception as e:
            logger.error(
                f"Transition failed: {current_state} --{trigger.value}--> ? "
                f"Error: {e}",
                exc_info=True
            )
            
            # Attempt error fallback
            try:
                self.error()
                self.record_transition(
                    state_from=current_state,
                    state_to=self.state,
                    trigger=TransitionTrigger.ERROR.value,
                    transition_data=transition_data,
                    error_message=str(e)
                )
            except Exception as fallback_error:
                logger.error(
                    f"Error fallback failed: {fallback_error}",
                    exc_info=True
                )
            
            return False
    
    def get_current_state(self) -> WorkflowState:
        """Get current state as enum."""
        return WorkflowState(self.state)
    
    def is_complete(self) -> bool:
        """Check if workflow is complete."""
        return self.state == WorkflowState.COMPLETE.value
    
    def is_error(self) -> bool:
        """Check if workflow is in error state."""
        return self.state == WorkflowState.ERROR_FALLBACK.value
    
    def get_audit_trail(self) -> List[StateTransitionAudit]:
        """Get full audit trail."""
        return self.audit_trail
    
    def get_workflow_summary(self) -> Dict[str, Any]:
        """
        Get summary of workflow execution.
        
        Returns:
            Dictionary with workflow statistics
        """
        if not self.audit_trail:
            return {
                "tenant_id": self.tenant_id,
                "query_id": self.query_id,
                "current_state": self.state,
                "total_transitions": 0,
                "total_duration_ms": 0,
                "status": "not_started"
            }
        
        total_duration = sum(
            audit.duration_ms or 0
            for audit in self.audit_trail
        )
        
        error_count = sum(
            1 for audit in self.audit_trail
            if audit.error_message
        )
        
        return {
            "tenant_id": self.tenant_id,
            "query_id": self.query_id,
            "current_state": self.state,
            "total_transitions": len(self.audit_trail),
            "total_duration_ms": total_duration,
            "error_count": error_count,
            "states_visited": [audit.state_to for audit in self.audit_trail],
            "status": "complete" if self.is_complete() else "error" if self.is_error() else "in_progress"
        }


# Convenience function for creating state machines
def create_workflow_state_machine(
    tenant_id: str,
    query_id: str
) -> OrchestratorStateMachine:
    """
    Create a new workflow state machine.
    
    Args:
        tenant_id: Tenant ID
        query_id: Query ID
    
    Returns:
        Initialized state machine
    """
    return OrchestratorStateMachine(
        tenant_id=tenant_id,
        query_id=query_id
    )

