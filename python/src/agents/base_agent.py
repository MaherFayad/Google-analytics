"""
Base agent class for Pydantic-AI agents.

Provides common functionality for all agents including:
- Logging and telemetry
- Error handling and retries
- Circuit breaker integration
- Async execution support
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from .schemas.results import AgentStatus

# Type variable for agent result types
TResult = TypeVar("TResult", bound=BaseModel)

logger = logging.getLogger(__name__)


class BaseAgent(ABC, Generic[TResult]):
    """
    Abstract base class for all Pydantic-AI agents.
    
    Provides:
    - Standardized agent initialization
    - Status tracking
    - Error handling
    - Async execution support
    - Logging and telemetry
    
    Usage:
        class MyAgent(BaseAgent[MyResult]):
            def __init__(self):
                super().__init__(name="my_agent")
                
            def get_system_prompt(self) -> str:
                return "You are a helpful assistant..."
                
            async def run_async(self, ctx: RunContext, **kwargs) -> MyResult:
                # Agent logic here
                return MyResult(...)
    """
    
    def __init__(
        self,
        name: str,
        model: str = "openai:gpt-4o",
        retries: int = 3,
        timeout_seconds: int = 30,
    ):
        """
        Initialize base agent.
        
        Args:
            name: Agent identifier (e.g., "data_fetcher", "embedding")
            model: LLM model to use (default: gpt-4o)
            retries: Number of retry attempts on failure
            timeout_seconds: Execution timeout in seconds
        """
        self.name = name
        self.model = model
        self.retries = retries
        self.timeout_seconds = timeout_seconds
        
        # Initialize status tracking
        self.status = AgentStatus(
            agent_name=name,
            status="pending"
        )
        
        # Create Pydantic-AI agent (will be configured by subclass)
        self._agent: Optional[Agent] = None
        
        logger.info(f"Initialized {name} agent with model {model}")
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Return the system prompt for this agent.
        
        Subclasses must implement this to define agent behavior.
        """
        pass
    
    @abstractmethod
    async def run_async(
        self,
        ctx: RunContext,
        **kwargs: Any
    ) -> TResult:
        """
        Execute agent logic asynchronously.
        
        Args:
            ctx: Pydantic-AI run context
            **kwargs: Agent-specific parameters
            
        Returns:
            Typed result (subclass of BaseModel)
        """
        pass
    
    async def execute(self, **kwargs: Any) -> TResult:
        """
        Execute agent with status tracking and error handling.
        
        This is the main entry point for agent execution.
        
        Args:
            **kwargs: Agent-specific parameters
            
        Returns:
            Typed result from agent execution
            
        Raises:
            Exception: If agent execution fails after retries
        """
        self.status.status = "running"
        self.status.started_at = datetime.utcnow()
        
        try:
            logger.info(f"Starting {self.name} agent execution")
            
            # Execute agent logic
            result = await self.run_async(None, **kwargs)  # type: ignore
            
            # Update status
            self.status.status = "success"
            self.status.completed_at = datetime.utcnow()
            
            logger.info(
                f"{self.name} agent completed in {self.status.duration_ms}ms"
            )
            
            return result
            
        except Exception as e:
            self.status.status = "failed"
            self.status.completed_at = datetime.utcnow()
            self.status.error_message = str(e)
            
            logger.error(
                f"{self.name} agent failed: {e}",
                exc_info=True,
                extra={
                    "agent": self.name,
                    "duration_ms": self.status.duration_ms,
                    "kwargs": kwargs,
                }
            )
            
            raise
    
    def get_status(self) -> AgentStatus:
        """Get current agent execution status."""
        return self.status
    
    def reset_status(self) -> None:
        """Reset agent status to pending."""
        self.status = AgentStatus(
            agent_name=self.name,
            status="pending"
        )


class AgentRegistry:
    """
    Registry for managing agent instances.
    
    Provides centralized agent lifecycle management and dependency injection.
    """
    
    _agents: Dict[str, BaseAgent] = {}
    
    @classmethod
    def register(cls, agent: BaseAgent) -> None:
        """Register an agent instance."""
        cls._agents[agent.name] = agent
        logger.info(f"Registered agent: {agent.name}")
    
    @classmethod
    def get(cls, name: str) -> Optional[BaseAgent]:
        """Get agent by name."""
        return cls._agents.get(name)
    
    @classmethod
    def list_agents(cls) -> list[str]:
        """List all registered agent names."""
        return list(cls._agents.keys())
    
    @classmethod
    def clear(cls) -> None:
        """Clear all registered agents (for testing)."""
        cls._agents.clear()

