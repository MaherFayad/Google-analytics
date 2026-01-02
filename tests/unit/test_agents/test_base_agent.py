"""
Unit tests for BaseAgent.

Tests the base agent functionality including:
- Status tracking
- Error handling
- Async execution
"""

import pytest
from datetime import datetime
from pydantic import BaseModel
from pydantic_ai import RunContext

from src.agents.base_agent import BaseAgent, AgentRegistry
from src.agents.schemas.results import AgentStatus


class TestResult(BaseModel):
    """Test result model."""
    value: str
    count: int


class TestAgent(BaseAgent[TestResult]):
    """Test agent implementation."""
    
    def get_system_prompt(self) -> str:
        return "Test agent prompt"
    
    async def run_async(self, ctx: RunContext, **kwargs) -> TestResult:
        """Test execution."""
        value = kwargs.get("value", "default")
        count = kwargs.get("count", 0)
        return TestResult(value=value, count=count)


class FailingAgent(BaseAgent[TestResult]):
    """Agent that always fails."""
    
    def get_system_prompt(self) -> str:
        return "Failing agent prompt"
    
    async def run_async(self, ctx: RunContext, **kwargs) -> TestResult:
        """Always raises an exception."""
        raise ValueError("Test error")


class TestBaseAgent:
    """Test suite for BaseAgent."""
    
    def test_agent_initialization(self):
        """Test agent can be initialized."""
        agent = TestAgent(name="test_agent")
        
        assert agent.name == "test_agent"
        assert agent.model == "openai:gpt-4o"
        assert agent.status.status == "pending"
        assert agent.status.agent_name == "test_agent"
    
    @pytest.mark.asyncio
    async def test_agent_execution_success(self):
        """Test successful agent execution."""
        agent = TestAgent(name="test_agent")
        
        result = await agent.execute(value="test", count=42)
        
        assert isinstance(result, TestResult)
        assert result.value == "test"
        assert result.count == 42
        assert agent.status.status == "success"
        assert agent.status.started_at is not None
        assert agent.status.completed_at is not None
        assert agent.status.duration_ms is not None
        assert agent.status.duration_ms >= 0
    
    @pytest.mark.asyncio
    async def test_agent_execution_failure(self):
        """Test agent execution with error."""
        agent = FailingAgent(name="failing_agent")
        
        with pytest.raises(ValueError, match="Test error"):
            await agent.execute()
        
        assert agent.status.status == "failed"
        assert agent.status.error_message == "Test error"
        assert agent.status.completed_at is not None
    
    def test_agent_status_tracking(self):
        """Test status tracking."""
        agent = TestAgent(name="test_agent")
        
        # Initial status
        status = agent.get_status()
        assert status.status == "pending"
        assert status.started_at is None
        
        # Reset status
        agent.status.status = "running"
        agent.reset_status()
        assert agent.status.status == "pending"
    
    def test_agent_registry(self):
        """Test agent registry."""
        AgentRegistry.clear()
        
        agent1 = TestAgent(name="agent1")
        agent2 = TestAgent(name="agent2")
        
        AgentRegistry.register(agent1)
        AgentRegistry.register(agent2)
        
        assert len(AgentRegistry.list_agents()) == 2
        assert AgentRegistry.get("agent1") == agent1
        assert AgentRegistry.get("agent2") == agent2
        assert AgentRegistry.get("nonexistent") is None
        
        AgentRegistry.clear()
        assert len(AgentRegistry.list_agents()) == 0

