"""
Unit tests for Agent Factory Service.

Implements Task 3.4: The Agent Factory Service

Tests:
1. Create agent with valid persona
2. Create agent with invalid persona
3. OAuth token retrieval
4. Custom persona configuration
5. List available personas
6. Validate user access
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from src.agents.agent_factory import (
    AgentFactory,
    ReportSchema,
    create_analytics_agent,
)
from src.server.config.personas import PersonaConfig


@pytest.fixture
def mock_session():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_auth_service():
    """Mock AuthService."""
    mock = AsyncMock()
    mock.get_valid_token = AsyncMock(return_value="mock_access_token_12345")
    return mock


@pytest.mark.asyncio
async def test_create_agent_with_valid_persona(mock_session, mock_auth_service):
    """
    Test creating agent with valid persona.
    
    Scenario:
        - User requests Product Owner persona
        - Expected: Agent created with PO configuration
    """
    factory = AgentFactory(mock_session, openai_api_key="test_key")
    factory.auth_service = mock_auth_service
    
    with patch('src.agents.agent_factory.ReportingAgent') as MockAgent:
        mock_agent = MockAgent.return_value
        mock_agent.register_tools = Mock()
        
        agent = await factory.create_agent(
            user_id="user_123",
            tenant_id="tenant_456",
            property_id="12345678",
            persona_key="po"
        )
        
        # Verify token was retrieved
        mock_auth_service.get_valid_token.assert_called_once_with("user_123")
        
        # Verify agent was created
        MockAgent.assert_called_once()
        
        # Verify tools were registered
        mock_agent.register_tools.assert_called_once()


@pytest.mark.asyncio
async def test_create_agent_with_invalid_persona(mock_session, mock_auth_service):
    """
    Test creating agent with invalid persona key.
    
    Scenario:
        - User requests non-existent persona
        - Expected: KeyError raised
    """
    factory = AgentFactory(mock_session)
    factory.auth_service = mock_auth_service
    
    with pytest.raises(KeyError) as exc_info:
        await factory.create_agent(
            user_id="user_123",
            tenant_id="tenant_456",
            property_id="12345678",
            persona_key="invalid_persona"
        )
    
    assert "invalid_persona" in str(exc_info.value)


@pytest.mark.asyncio
async def test_oauth_token_retrieval_failure(mock_session):
    """
    Test handling of OAuth token retrieval failure.
    
    Scenario:
        - AuthService fails to get token
        - Expected: Exception raised with clear message
    """
    factory = AgentFactory(mock_session)
    
    # Mock failed token retrieval
    mock_auth = AsyncMock()
    mock_auth.get_valid_token = AsyncMock(
        side_effect=Exception("Token expired")
    )
    factory.auth_service = mock_auth
    
    with pytest.raises(Exception) as exc_info:
        await factory.create_agent(
            user_id="user_123",
            tenant_id="tenant_456",
            property_id="12345678",
            persona_key="po"
        )
    
    assert "Authentication failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_agent_with_custom_persona(mock_session, mock_auth_service):
    """
    Test creating agent with custom persona configuration.
    
    Scenario:
        - User provides custom PersonaConfig
        - Expected: Agent created with custom configuration
    """
    factory = AgentFactory(mock_session)
    factory.auth_service = mock_auth_service
    
    custom_persona = PersonaConfig(
        key="custom",
        name="Custom Analyst",
        role="Specialized Analyst",
        goal="Custom analysis goal",
        backstory="Custom backstory for testing",
        focus_areas=["custom", "metrics"],
        preferred_visualizations=["line", "bar"],
        tone="Professional"
    )
    
    with patch('src.agents.agent_factory.ReportingAgent') as MockAgent:
        mock_agent = MockAgent.return_value
        mock_agent.register_tools = Mock()
        
        agent = await factory.create_agent_with_custom_persona(
            user_id="user_123",
            tenant_id="tenant_456",
            property_id="12345678",
            custom_persona=custom_persona
        )
        
        # Verify agent was created
        MockAgent.assert_called_once()
        
        # Verify custom persona was used
        call_kwargs = MockAgent.call_args[1]
        assert call_kwargs['persona_config'] == custom_persona


@pytest.mark.asyncio
async def test_list_available_personas(mock_session):
    """
    Test listing available personas.
    
    Scenario:
        - Request list of personas
        - Expected: List of all registered personas
    """
    factory = AgentFactory(mock_session)
    
    personas = await factory.list_available_personas()
    
    # Verify personas list
    assert isinstance(personas, list)
    assert len(personas) > 0
    
    # Verify structure
    for persona in personas:
        assert "key" in persona
        assert "name" in persona
        assert "role" in persona
    
    # Verify expected personas
    persona_keys = [p["key"] for p in personas]
    assert "po" in persona_keys  # Product Owner
    assert "ux" in persona_keys  # UX Designer
    assert "mgr" in persona_keys  # Manager


@pytest.mark.asyncio
async def test_validate_user_access_success(mock_session, mock_auth_service):
    """
    Test validating user access to GA4 property.
    
    Scenario:
        - User has valid credentials and property access
        - Expected: Returns True
    """
    factory = AgentFactory(mock_session)
    factory.auth_service = mock_auth_service
    
    with patch('src.agents.agent_factory.get_ga4_property_info') as mock_get_info:
        mock_get_info.return_value = {"name": "Test Property"}
        
        has_access = await factory.validate_user_access(
            user_id="user_123",
            tenant_id="tenant_456",
            property_id="12345678"
        )
        
        assert has_access is True


@pytest.mark.asyncio
async def test_validate_user_access_failure(mock_session):
    """
    Test validating user access when user lacks permissions.
    
    Scenario:
        - User does not have access to property
        - Expected: Returns False
    """
    factory = AgentFactory(mock_session)
    
    # Mock failed access
    mock_auth = AsyncMock()
    mock_auth.get_valid_token = AsyncMock(
        side_effect=Exception("Access denied")
    )
    factory.auth_service = mock_auth
    
    has_access = await factory.validate_user_access(
        user_id="user_123",
        tenant_id="tenant_456",
        property_id="12345678"
    )
    
    assert has_access is False


@pytest.mark.asyncio
async def test_convenience_function(mock_session, mock_auth_service):
    """
    Test convenience function for quick agent creation.
    
    Scenario:
        - Use create_analytics_agent helper function
        - Expected: Agent created successfully
    """
    with patch('src.agents.agent_factory.AgentFactory') as MockFactory:
        mock_factory = MockFactory.return_value
        mock_factory.create_agent = AsyncMock(return_value=Mock())
        
        agent = await create_analytics_agent(
            session=mock_session,
            user_id="user_123",
            tenant_id="tenant_456",
            property_id="12345678",
            persona_key="po"
        )
        
        # Verify factory was created
        MockFactory.assert_called_once_with(mock_session)
        
        # Verify create_agent was called
        mock_factory.create_agent.assert_called_once_with(
            user_id="user_123",
            tenant_id="tenant_456",
            property_id="12345678",
            persona_key="po"
        )


def test_report_schema_structure():
    """
    Test ReportSchema structure.
    
    Scenario:
        - Create ReportSchema instance
        - Expected: All required fields present
    """
    report = ReportSchema(
        answer="Test answer",
        charts=[
            {
                "type": "line",
                "title": "Test Chart",
                "data": [{"x": 1, "y": 2}]
            }
        ],
        metrics=[
            {
                "label": "Sessions",
                "value": "10,234",
                "change": "+15%"
            }
        ],
        insights=["Insight 1", "Insight 2"],
        metadata={"date_range": "2025-01-01 to 2025-01-07"}
    )
    
    # Verify structure
    assert report.answer == "Test answer"
    assert len(report.charts) == 1
    assert len(report.metrics) == 1
    assert len(report.insights) == 2
    assert "date_range" in report.metadata
    assert isinstance(report.timestamp, datetime)


@pytest.mark.asyncio
async def test_ga4_context_creation(mock_session, mock_auth_service):
    """
    Test GA4 tool context is created correctly.
    
    Scenario:
        - Create agent
        - Expected: GA4ToolContext has correct tenant/user/property IDs
    """
    factory = AgentFactory(mock_session)
    factory.auth_service = mock_auth_service
    
    with patch('src.agents.agent_factory.ReportingAgent') as MockAgent:
        mock_agent = MockAgent.return_value
        mock_agent.register_tools = Mock()
        
        await factory.create_agent(
            user_id="user_123",
            tenant_id="tenant_456",
            property_id="12345678",
            persona_key="po"
        )
        
        # Verify register_tools was called with GA4ToolContext
        mock_agent.register_tools.assert_called_once()
        
        ga4_context = mock_agent.register_tools.call_args[0][0]
        assert ga4_context.tenant_id == "tenant_456"
        assert ga4_context.user_id == "user_123"
        assert ga4_context.property_id == "12345678"
        assert ga4_context.access_token == "mock_access_token_12345"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

