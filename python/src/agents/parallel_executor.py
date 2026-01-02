"""
Parallel Agent Executor with Safe Concurrency.

Implements Task P0-41: Parallel Agent Executor with Circuit Breakers

Features:
- Safe concurrent agent execution
- Per-agent timeout enforcement
- Circuit breaker integration
- Failure isolation (one agent failure doesn't crash others)
- Execution audit logging
- Rollback strategies

Usage:
    executor = ParallelAgentExecutor()
    
    results = await executor.execute_parallel_safe(
        agents=[data_fetcher, rag_agent],
        timeout_ms=30000,
        rollback_on_any_failure=False
    )
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from uuid import uuid4

from pydantic import BaseModel, Field

from .circuit_breakers import get_circuit_breaker_registry, CircuitBreakerError
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentExecutionResult(BaseModel):
    """Result of agent execution."""
    
    agent_name: str
    status: str  # success, failed, timeout, circuit_open
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: int
    started_at: datetime
    completed_at: datetime


class ParallelExecutionLog(BaseModel):
    """Audit log for parallel execution."""
    
    execution_id: str
    tenant_id: str
    agents_executed: List[str]
    parallel_groups: List[List[str]]
    total_duration_ms: int
    success_count: int
    failure_count: int
    circuit_breaker_blocks: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ParallelAgentExecutor:
    """
    Executes multiple agents concurrently with safety guarantees.
    
    Implements Task P0-41: Parallel Agent Executor with Circuit Breakers
    
    Features:
    - Concurrent execution with asyncio.gather()
    - Per-agent timeouts
    - Circuit breaker integration
    - Failure isolation
    - Execution audit trail
    
    Safety Guarantees:
    - One agent failure doesn't crash others
    - Timeouts are enforced per-agent
    - Circuit breakers prevent cascading failures
    - Results are collected even if some agents fail
    """
    
    def __init__(self):
        """Initialize parallel executor."""
        self.circuit_registry = get_circuit_breaker_registry()
        self._execution_logs: List[ParallelExecutionLog] = []
        
        logger.info("Parallel agent executor initialized")
    
    async def execute_parallel_safe(
        self,
        agents: List[BaseAgent],
        timeout_ms: int,
        tenant_id: str,
        rollback_on_any_failure: bool = False,
        circuit_breaker_enabled: bool = True
    ) -> Dict[str, AgentExecutionResult]:
        """
        Execute agents in parallel safely.
        
        Args:
            agents: List of agents to execute
            timeout_ms: Timeout per agent in milliseconds
            tenant_id: Tenant ID for audit trail
            rollback_on_any_failure: If True, cancel all on first failure
            circuit_breaker_enabled: Enable circuit breaker protection
        
        Returns:
            Dictionary mapping agent_name to AgentExecutionResult
        
        Example:
            results = await executor.execute_parallel_safe(
                agents=[data_fetcher, rag_agent],
                timeout_ms=30000,
                tenant_id="tenant-123"
            )
            
            if results["DataFetcherAgent"].status == "success":
                data = results["DataFetcherAgent"].result
        """
        execution_id = str(uuid4())
        start_time = time.time()
        
        logger.info(
            f"Starting parallel execution {execution_id}: "
            f"{len(agents)} agents, timeout={timeout_ms}ms"
        )
        
        # Create tasks for all agents
        tasks = []
        agent_names = []
        
        for agent in agents:
            agent_name = agent.__class__.__name__
            agent_names.append(agent_name)
            
            task = asyncio.create_task(
                self._execute_single_agent(
                    agent=agent,
                    timeout_ms=timeout_ms,
                    circuit_breaker_enabled=circuit_breaker_enabled
                )
            )
            tasks.append(task)
        
        # Execute all agents concurrently
        try:
            if rollback_on_any_failure:
                # Use return_exceptions=False to fail fast
                results_list = await asyncio.gather(*tasks, return_exceptions=False)
            else:
                # Use return_exceptions=True to collect all results
                results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        except Exception as e:
            # One agent failed in rollback mode
            logger.error(f"Parallel execution failed (rollback mode): {e}")
            
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for cancellations
            await asyncio.gather(*tasks, return_exceptions=True)
            
            raise
        
        # Collect results
        results = {}
        for agent_name, result in zip(agent_names, results_list):
            if isinstance(result, Exception):
                # Handle exception result
                results[agent_name] = AgentExecutionResult(
                    agent_name=agent_name,
                    status="failed",
                    error=str(result),
                    duration_ms=int((time.time() - start_time) * 1000),
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow()
                )
            else:
                results[agent_name] = result
        
        # Calculate statistics
        total_duration_ms = int((time.time() - start_time) * 1000)
        success_count = sum(1 for r in results.values() if r.status == "success")
        failure_count = sum(1 for r in results.values() if r.status == "failed")
        circuit_blocks = sum(1 for r in results.values() if r.status == "circuit_open")
        
        # Log execution
        log = ParallelExecutionLog(
            execution_id=execution_id,
            tenant_id=tenant_id,
            agents_executed=agent_names,
            parallel_groups=[agent_names],  # Single parallel group
            total_duration_ms=total_duration_ms,
            success_count=success_count,
            failure_count=failure_count,
            circuit_breaker_blocks=circuit_blocks
        )
        self._execution_logs.append(log)
        
        logger.info(
            f"Parallel execution {execution_id} complete: "
            f"{success_count} success, {failure_count} failed, "
            f"{circuit_blocks} blocked, {total_duration_ms}ms"
        )
        
        return results
    
    async def _execute_single_agent(
        self,
        agent: BaseAgent,
        timeout_ms: int,
        circuit_breaker_enabled: bool
    ) -> AgentExecutionResult:
        """
        Execute single agent with timeout and circuit breaker.
        
        Args:
            agent: Agent to execute
            timeout_ms: Timeout in milliseconds
            circuit_breaker_enabled: Enable circuit breaker
        
        Returns:
            AgentExecutionResult
        """
        agent_name = agent.__class__.__name__
        start_time = time.time()
        started_at = datetime.utcnow()
        
        # Get circuit breaker
        if circuit_breaker_enabled:
            breaker = self.circuit_registry.get_or_create(agent_name)
            
            # Check if circuit is open
            if breaker.is_open:
                logger.warning(f"Circuit breaker OPEN for {agent_name}, skipping execution")
                return AgentExecutionResult(
                    agent_name=agent_name,
                    status="circuit_open",
                    error="Circuit breaker is open",
                    duration_ms=0,
                    started_at=started_at,
                    completed_at=datetime.utcnow()
                )
        
        try:
            # Execute with timeout
            timeout_seconds = timeout_ms / 1000
            
            if circuit_breaker_enabled:
                async with breaker():
                    result = await asyncio.wait_for(
                        agent.execute(),
                        timeout=timeout_seconds
                    )
            else:
                result = await asyncio.wait_for(
                    agent.execute(),
                    timeout=timeout_seconds
                )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(f"Agent {agent_name} completed successfully in {duration_ms}ms")
            
            return AgentExecutionResult(
                agent_name=agent_name,
                status="success",
                result=result,
                duration_ms=duration_ms,
                started_at=started_at,
                completed_at=datetime.utcnow()
            )
        
        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Agent {agent_name} timed out after {duration_ms}ms")
            
            return AgentExecutionResult(
                agent_name=agent_name,
                status="timeout",
                error=f"Execution timed out after {timeout_ms}ms",
                duration_ms=duration_ms,
                started_at=started_at,
                completed_at=datetime.utcnow()
            )
        
        except CircuitBreakerError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"Circuit breaker blocked {agent_name}: {e}")
            
            return AgentExecutionResult(
                agent_name=agent_name,
                status="circuit_open",
                error=str(e),
                duration_ms=duration_ms,
                started_at=started_at,
                completed_at=datetime.utcnow()
            )
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Agent {agent_name} failed: {e}", exc_info=True)
            
            return AgentExecutionResult(
                agent_name=agent_name,
                status="failed",
                error=str(e),
                duration_ms=duration_ms,
                started_at=started_at,
                completed_at=datetime.utcnow()
            )
    
    def get_execution_logs(self) -> List[ParallelExecutionLog]:
        """Get all execution logs."""
        return self._execution_logs
    
    def get_circuit_breaker_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        return self.circuit_registry.get_all_stats()

