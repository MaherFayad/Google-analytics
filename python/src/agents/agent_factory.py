"""
Agent Factory Service for Creating Persona-Based Analytics Agents.

Implements Task 3.4: The Agent Factory Service (Updated for Pydantic-AI)

IMPORTANT: This implementation uses Pydantic-AI instead of CrewAI as per
Task P0-17 (Agent Framework Unification). The original task description
referenced CrewAI, but the codebase has migrated to Pydantic-AI.

The Agent Factory creates specialized analytics agents configured with
different personas (Product Owner, UX Designer, Manager, etc.) that tailor
reporting style and focus areas to different professional roles.

Features:
- Persona-based agent configuration
- OAuth token management via AuthService
- Multi-tenant isolation
- Type-safe with Pydantic V2
- Async-first architecture

Example Usage:
    ```python
    factory = AgentFactory(session)
    
    agent = await factory.create_agent(
        user_id="user_123",
        tenant_id="tenant_456",
        persona_key="po",  # Product Owner
        property_id="GA4_PROPERTY_ID"
    )
    
    result = await agent.run(
        "Show me mobile conversion trends last week"
    )
    ```
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from sqlalchemy.ext.asyncio import AsyncSession

from ..server.services.auth import AuthService
from ..server.config.personas import (
    get_persona,
    get_agent_parameters,
    PersonaConfig,
    DEFAULT_PERSONA_KEY,
)
from .tools.ga4_tool import GA4ToolContext, fetch_ga4_data, get_ga4_property_info
from .reporting_agent import ReportingAgent
from ..server.core.config import settings

logger = logging.getLogger(__name__)


class ReportSchema(BaseModel):
    """
    Output schema for analytics reports.
    
    Implements Task 3.2: Pydantic Output Models
    
    This structured schema ensures consistent report format across
    all personas and enables frontend to render charts and metrics.
    """
    
    answer: str = Field(
        description="Natural language answer to the user's query"
    )
    
    charts: list[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of chart configurations for visualization"
    )
    
    metrics: list[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of metric cards (KPIs)"
    )
    
    insights: list[str] = Field(
        default_factory=list,
        description="Key insights and recommendations"
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (date range, data source, etc.)"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Report generation timestamp"
    )


class AgentFactory:
    """
    Factory for creating persona-based analytics agents.
    
    The factory handles:
    1. OAuth token retrieval via AuthService
    2. Persona configuration loading
    3. GA4 tool context setup
    4. Agent instantiation with persona parameters
    
    Example:
        ```python
        factory = AgentFactory(db_session)
        
        # Create Product Owner agent
        po_agent = await factory.create_agent(
            user_id="user_123",
            tenant_id="tenant_456",
            persona_key="po",
            property_id="12345678"
        )
        
        # Run query
        result = await po_agent.run(
            "What are the top 3 features by engagement?"
        )
        ```
    """
    
    def __init__(
        self,
        session: AsyncSession,
        openai_api_key: Optional[str] = None
    ):
        """
        Initialize Agent Factory.
        
        Args:
            session: Database session for AuthService
            openai_api_key: OpenAI API key (defaults to settings.OPENAI_API_KEY)
        """
        self.session = session
        self.openai_api_key = openai_api_key or settings.OPENAI_API_KEY
        self.auth_service = AuthService(session)
        
        logger.info("Agent Factory initialized")
    
    async def create_agent(
        self,
        user_id: str,
        tenant_id: str,
        property_id: str,
        persona_key: str = DEFAULT_PERSONA_KEY,
        query: Optional[str] = None,
    ) -> ReportingAgent:
        """
        Create a persona-based analytics agent.
        
        Workflow:
        1. Get valid OAuth access token via AuthService
        2. Load persona configuration
        3. Create GA4 tool context
        4. Instantiate ReportingAgent with persona parameters
        5. Register GA4 tools
        
        Args:
            user_id: User ID for authentication
            tenant_id: Tenant ID for multi-tenant isolation
            property_id: GA4 property ID
            persona_key: Persona identifier (po, ux, mgr, da, mkt)
            query: Optional query for context (not used in creation)
            
        Returns:
            Configured ReportingAgent ready for execution
            
        Raises:
            KeyError: If persona_key not found
            Exception: If token retrieval fails
            
        Example:
            ```python
            agent = await factory.create_agent(
                user_id="user_123",
                tenant_id="tenant_456",
                property_id="12345678",
                persona_key="po"
            )
            ```
        """
        logger.info(
            f"Creating agent for user {user_id}",
            extra={
                "tenant_id": tenant_id,
                "persona_key": persona_key,
                "property_id": property_id,
            }
        )
        
        # Step 1: Get valid OAuth access token
        try:
            access_token = await self.auth_service.get_valid_token(user_id)
            logger.debug(f"Retrieved access token for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to get access token for user {user_id}: {e}")
            raise Exception(f"Authentication failed: {str(e)}")
        
        # Step 2: Load persona configuration
        try:
            persona = get_persona(persona_key)
            persona_params = get_agent_parameters(persona_key)
            logger.info(f"Loaded persona: {persona.name}")
        except KeyError as e:
            logger.error(f"Invalid persona key: {persona_key}")
            raise
        
        # Step 3: Create GA4 tool context
        ga4_context = GA4ToolContext(
            tenant_id=tenant_id,
            user_id=user_id,
            property_id=property_id,
            access_token=access_token,
        )
        
        # Step 4: Create ReportingAgent with persona parameters
        agent = ReportingAgent(
            openai_api_key=self.openai_api_key,
            persona_config=persona,
            result_type=ReportSchema,
        )
        
        # Step 5: Register GA4 tools with context
        # Note: Tools are registered with the agent's Pydantic-AI Agent instance
        agent.register_tools(ga4_context)
        
        logger.info(
            f"Agent created successfully",
            extra={
                "persona": persona.name,
                "user_id": user_id,
                "tenant_id": tenant_id,
            }
        )
        
        return agent
    
    async def create_agent_with_custom_persona(
        self,
        user_id: str,
        tenant_id: str,
        property_id: str,
        custom_persona: PersonaConfig,
    ) -> ReportingAgent:
        """
        Create agent with custom persona configuration.
        
        Useful for A/B testing new personas or creating specialized
        one-off agents without adding to the registry.
        
        Args:
            user_id: User ID for authentication
            tenant_id: Tenant ID for isolation
            property_id: GA4 property ID
            custom_persona: Custom PersonaConfig
            
        Returns:
            Configured ReportingAgent
            
        Example:
            ```python
            custom = PersonaConfig(
                key="custom",
                name="Custom Analyst",
                role="Specialized Analyst",
                goal="Custom analysis goal",
                backstory="Custom backstory...",
                focus_areas=["custom", "areas"],
                preferred_visualizations=["line", "bar"],
                tone="Custom tone"
            )
            
            agent = await factory.create_agent_with_custom_persona(
                user_id="user_123",
                tenant_id="tenant_456",
                property_id="12345678",
                custom_persona=custom
            )
            ```
        """
        logger.info(f"Creating agent with custom persona: {custom_persona.name}")
        
        # Get access token
        access_token = await self.auth_service.get_valid_token(user_id)
        
        # Create GA4 context
        ga4_context = GA4ToolContext(
            tenant_id=tenant_id,
            user_id=user_id,
            property_id=property_id,
            access_token=access_token,
        )
        
        # Create agent with custom persona
        agent = ReportingAgent(
            openai_api_key=self.openai_api_key,
            persona_config=custom_persona,
            result_type=ReportSchema,
        )
        
        agent.register_tools(ga4_context)
        
        return agent
    
    async def list_available_personas(self) -> list[Dict[str, str]]:
        """
        List all available personas.
        
        Returns:
            List of persona summaries
            
        Example:
            ```python
            personas = await factory.list_available_personas()
            # [
            #   {"key": "po", "name": "Product Owner", "role": "Strategic Product Manager"},
            #   {"key": "ux", "name": "UX Designer", "role": "User Experience Designer"},
            #   ...
            # ]
            ```
        """
        from ..server.config.personas import list_personas
        return list_personas()
    
    async def validate_user_access(
        self,
        user_id: str,
        tenant_id: str,
        property_id: str
    ) -> bool:
        """
        Validate that user has access to the GA4 property.
        
        Args:
            user_id: User ID
            tenant_id: Tenant ID
            property_id: GA4 property ID
            
        Returns:
            True if user has access, False otherwise
            
        Example:
            ```python
            has_access = await factory.validate_user_access(
                user_id="user_123",
                tenant_id="tenant_456",
                property_id="12345678"
            )
            ```
        """
        try:
            # Try to get access token
            access_token = await self.auth_service.get_valid_token(user_id)
            
            # Try to fetch property info
            ga4_context = GA4ToolContext(
                tenant_id=tenant_id,
                user_id=user_id,
                property_id=property_id,
                access_token=access_token,
            )
            
            # Create minimal agent to test access
            from pydantic_ai import RunContext
            ctx = RunContext(deps=ga4_context)
            
            await get_ga4_property_info(ctx)
            
            logger.info(f"User {user_id} has access to property {property_id}")
            return True
            
        except Exception as e:
            logger.warning(
                f"User {user_id} does not have access to property {property_id}: {e}"
            )
            return False


# Convenience function for quick agent creation
async def create_analytics_agent(
    session: AsyncSession,
    user_id: str,
    tenant_id: str,
    property_id: str,
    persona_key: str = DEFAULT_PERSONA_KEY,
) -> ReportingAgent:
    """
    Convenience function to create an analytics agent.
    
    Args:
        session: Database session
        user_id: User ID
        tenant_id: Tenant ID
        property_id: GA4 property ID
        persona_key: Persona identifier
        
    Returns:
        Configured ReportingAgent
        
    Example:
        ```python
        agent = await create_analytics_agent(
            session=db_session,
            user_id="user_123",
            tenant_id="tenant_456",
            property_id="12345678",
            persona_key="po"
        )
        
        result = await agent.run("Show me mobile conversions")
        ```
    """
    factory = AgentFactory(session)
    return await factory.create_agent(
        user_id=user_id,
        tenant_id=tenant_id,
        property_id=property_id,
        persona_key=persona_key,
    )

