"""
Unit tests for persona configuration registry.

Tests Task 3.3: Persona Configuration Registry

Verifies:
- All personas are properly configured
- Persona lookup works correctly
- Agent parameters can be extracted
- Backstories encourage data visualization
"""

import pytest

from src.server.config.personas import (
    PersonaConfig,
    PERSONA_REGISTRY,
    get_persona,
    list_personas,
    get_agent_parameters,
    DEFAULT_PERSONA_KEY,
    PRODUCT_OWNER_PERSONA,
    UX_DESIGNER_PERSONA,
    MANAGER_PERSONA,
    DATA_ANALYST_PERSONA,
    MARKETING_PERSONA,
)


class TestPersonaStructure:
    """Test persona structure and required fields."""
    
    def test_all_personas_have_required_fields(self):
        """Test all personas have required fields populated."""
        required_fields = [
            "key", "name", "role", "goal", "backstory",
            "focus_areas", "preferred_visualizations", "tone"
        ]
        
        for persona in PERSONA_REGISTRY.values():
            for field in required_fields:
                value = getattr(persona, field)
                assert value is not None, f"Persona {persona.key} missing {field}"
                assert value != "", f"Persona {persona.key} has empty {field}"
    
    def test_backstories_encourage_visualization(self):
        """Test all backstories explicitly mention data visualization."""
        visualization_keywords = [
            "visualization", "visualizations", "chart", "charts",
            "graph", "graphs", "visual", "visually"
        ]
        
        for persona in PERSONA_REGISTRY.values():
            backstory_lower = persona.backstory.lower()
            has_visualization = any(
                keyword in backstory_lower
                for keyword in visualization_keywords
            )
            
            assert has_visualization, (
                f"Persona {persona.key} ({persona.name}) backstory "
                f"doesn't explicitly mention data visualization"
            )
    
    def test_all_personas_have_preferred_visualizations(self):
        """Test all personas specify preferred visualization types."""
        valid_chart_types = ["line", "bar", "pie", "area", "scatter"]
        
        for persona in PERSONA_REGISTRY.values():
            assert len(persona.preferred_visualizations) > 0, (
                f"Persona {persona.key} has no preferred visualizations"
            )
            
            # Verify all are valid chart types
            for viz in persona.preferred_visualizations:
                assert viz in valid_chart_types, (
                    f"Persona {persona.key} has invalid visualization type: {viz}"
                )


class TestPersonaRegistry:
    """Test persona registry functionality."""
    
    def test_registry_contains_all_personas(self):
        """Test registry contains expected personas."""
        expected_keys = ["po", "ux", "mgr", "da", "mkt"]
        
        for key in expected_keys:
            assert key in PERSONA_REGISTRY, f"Missing persona: {key}"
    
    def test_get_persona_valid_key(self):
        """Test getting persona with valid key."""
        persona = get_persona("po")
        assert persona.key == "po"
        assert persona.name == "Product Owner"
        assert isinstance(persona, PersonaConfig)
    
    def test_get_persona_invalid_key(self):
        """Test getting persona with invalid key raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            get_persona("invalid")
        
        assert "not found" in str(exc_info.value)
        assert "Available personas" in str(exc_info.value)
    
    def test_list_personas(self):
        """Test listing all personas."""
        personas = list_personas()
        
        assert len(personas) == 5  # po, ux, mgr, da, mkt
        
        # Verify structure
        for persona in personas:
            assert "key" in persona
            assert "name" in persona
            assert "role" in persona
    
    def test_default_persona_exists(self):
        """Test default persona key is valid."""
        assert DEFAULT_PERSONA_KEY in PERSONA_REGISTRY
        default = get_persona(DEFAULT_PERSONA_KEY)
        assert default.key == "da"  # Data Analyst


class TestAgentParameterExtraction:
    """Test extracting agent parameters from persona."""
    
    def test_get_agent_parameters(self):
        """Test extracting parameters for agent initialization."""
        params = get_agent_parameters("po")
        
        # Verify all required fields present
        assert "role" in params
        assert "goal" in params
        assert "backstory" in params
        assert "focus_areas" in params
        assert "preferred_visualizations" in params
        assert "tone" in params
        
        # Verify values match persona
        assert params["role"] == PRODUCT_OWNER_PERSONA.role
        assert params["goal"] == PRODUCT_OWNER_PERSONA.goal


class TestProductOwnerPersona:
    """Test Product Owner persona specifics."""
    
    def test_po_focuses_on_product_metrics(self):
        """Test PO persona focuses on product-relevant metrics."""
        po = PRODUCT_OWNER_PERSONA
        
        focus_areas_text = " ".join(po.focus_areas).lower()
        
        # Should mention product-relevant terms
        product_terms = ["engagement", "adoption", "conversion", "retention"]
        for term in product_terms:
            assert term in focus_areas_text
    
    def test_po_backstory_mentions_features(self):
        """Test PO backstory emphasizes feature analysis."""
        backstory_lower = PRODUCT_OWNER_PERSONA.backstory.lower()
        
        assert "feature" in backstory_lower
        assert "user" in backstory_lower
        assert "product" in backstory_lower


class TestUXDesignerPersona:
    """Test UX Designer persona specifics."""
    
    def test_ux_focuses_on_user_experience(self):
        """Test UX persona focuses on experience metrics."""
        ux = UX_DESIGNER_PERSONA
        
        focus_areas_text = " ".join(ux.focus_areas).lower()
        
        # Should mention UX-relevant terms
        ux_terms = ["bounce", "flow", "engagement", "interaction"]
        for term in ux_terms:
            assert term in focus_areas_text
    
    def test_ux_backstory_mentions_usability(self):
        """Test UX backstory emphasizes usability."""
        backstory_lower = UX_DESIGNER_PERSONA.backstory.lower()
        
        assert "usability" in backstory_lower or "user experience" in backstory_lower
        assert "flow" in backstory_lower


class TestManagerPersona:
    """Test Manager persona specifics."""
    
    def test_mgr_focuses_on_kpis(self):
        """Test Manager persona focuses on KPIs."""
        mgr = MANAGER_PERSONA
        
        focus_areas_text = " ".join(mgr.focus_areas).lower()
        
        assert "kpi" in focus_areas_text
        assert "business" in focus_areas_text or "outcome" in focus_areas_text
    
    def test_mgr_tone_is_executive(self):
        """Test Manager tone is executive-level."""
        assert "executive" in MANAGER_PERSONA.tone.lower()


class TestDataAnalystPersona:
    """Test Data Analyst persona specifics."""
    
    def test_da_focuses_on_detailed_analysis(self):
        """Test Data Analyst focuses on detailed metrics."""
        da = DATA_ANALYST_PERSONA
        
        focus_areas_text = " ".join(da.focus_areas).lower()
        
        # Should mention analytical terms
        analytical_terms = ["statistical", "analysis", "correlation", "anomaly"]
        found_terms = sum(1 for term in analytical_terms if term in focus_areas_text)
        assert found_terms >= 2  # At least 2 analytical terms
    
    def test_da_is_default_persona(self):
        """Test Data Analyst is the default persona."""
        assert DEFAULT_PERSONA_KEY == "da"


class TestMarketingPersona:
    """Test Marketing Manager persona specifics."""
    
    def test_mkt_focuses_on_campaigns(self):
        """Test Marketing persona focuses on campaigns and acquisition."""
        mkt = MARKETING_PERSONA
        
        focus_areas_text = " ".join(mkt.focus_areas).lower()
        
        # Should mention marketing terms
        marketing_terms = ["campaign", "acquisition", "conversion", "source"]
        found_terms = sum(1 for term in marketing_terms if term in focus_areas_text)
        assert found_terms >= 2
    
    def test_mkt_backstory_mentions_roi(self):
        """Test Marketing backstory emphasizes ROI."""
        backstory_lower = MARKETING_PERSONA.backstory.lower()
        
        assert "roi" in backstory_lower or "return on investment" in backstory_lower


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

