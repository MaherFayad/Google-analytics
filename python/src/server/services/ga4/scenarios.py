"""
Pre-defined test scenarios for GA4 Mock Service.

Implements Task P0-10: GA4 API Mock Service for Development

This module provides realistic test scenarios for comprehensive testing:
- Steady growth: Normal business growth
- Conversion drop: Alert/anomaly testing
- Traffic spike: Load testing scenarios
- Seasonal low: Off-peak traffic patterns
- High performance: Best-case scenarios

Usage:
    from server.services.ga4.scenarios import SCENARIOS, get_scenario
    
    scenario = get_scenario("conversion_drop")
    client = GA4MockService(property_id="...", tenant_id=uuid, scenario="conversion_drop")
"""

from typing import Dict, Any, List


# Scenario definitions
SCENARIOS: Dict[str, Dict[str, Any]] = {
    "steady_growth": {
        "name": "Steady Growth",
        "description": "Healthy business with consistent 5% week-over-week growth",
        "base_sessions": 10000,
        "growth_rate": 0.05,  # 5% WoW
        "conversion_rate": 0.03,  # 3%
        "bounce_rate": 0.42,  # 42%
        "avg_order_value": 75.00,
        "use_cases": [
            "Baseline testing",
            "Normal operations validation",
            "Trend analysis testing"
        ]
    },
    
    "conversion_drop": {
        "name": "Conversion Drop Alert",
        "description": "Sudden 50% drop in conversion rate - testing alert systems",
        "base_sessions": 15000,
        "growth_rate": 0.02,
        "conversion_rate": 0.015,  # Dropped from 3% to 1.5%
        "bounce_rate": 0.52,  # Increased from 42% to 52%
        "avg_order_value": 65.00,  # Slightly lower
        "use_cases": [
            "Alert system testing",
            "Anomaly detection validation",
            "Performance degradation scenarios"
        ],
        "notes": "Simulates checkout flow issues or pricing concerns"
    },
    
    "traffic_spike": {
        "name": "Viral Traffic Spike",
        "description": "5x traffic spike from viral content or marketing campaign",
        "base_sessions": 50000,  # 5x normal
        "growth_rate": 0.0,  # Spike plateaus
        "conversion_rate": 0.025,  # Slightly lower (new visitors)
        "bounce_rate": 0.48,  # Higher (less targeted)
        "avg_order_value": 70.00,
        "use_cases": [
            "Load testing",
            "Scalability validation",
            "Rate limiting testing"
        ],
        "notes": "Tests system behavior under sudden load"
    },
    
    "seasonal_low": {
        "name": "Off-Season Low Traffic",
        "description": "50% traffic reduction during off-season",
        "base_sessions": 5000,
        "growth_rate": -0.03,  # Declining 3% per week
        "conversion_rate": 0.035,  # Higher quality traffic
        "bounce_rate": 0.38,  # Lower (more engaged)
        "avg_order_value": 85.00,  # Higher AOV from loyal customers
        "use_cases": [
            "Seasonal pattern testing",
            "Quality over quantity scenarios",
            "Resource optimization testing"
        ]
    },
    
    "high_performance": {
        "name": "Best-Case Performance",
        "description": "Ideal metrics - 10% growth, 5% conversion, low bounce",
        "base_sessions": 25000,
        "growth_rate": 0.10,  # 10% WoW growth
        "conversion_rate": 0.05,  # 5% conversion
        "bounce_rate": 0.30,  # Low bounce rate
        "avg_order_value": 95.00,  # High AOV
        "use_cases": [
            "Goal-setting benchmarks",
            "Optimization target testing",
            "Best-case scenario validation"
        ],
        "notes": "Represents optimized funnel and messaging"
    },
    
    "mobile_vs_desktop": {
        "name": "Mobile-First Traffic",
        "description": "70% mobile traffic with lower conversion on mobile",
        "base_sessions": 12000,
        "growth_rate": 0.04,
        "conversion_rate": 0.025,
        "bounce_rate": 0.45,
        "avg_order_value": 68.00,
        "device_weights": {
            "mobile": 0.70,  # 70% mobile (vs 55% default)
            "desktop": 0.25,
            "tablet": 0.05
        },
        "conversion_by_device": {
            "mobile": 0.02,  # 2% on mobile
            "desktop": 0.04,  # 4% on desktop
            "tablet": 0.03  # 3% on tablet
        },
        "use_cases": [
            "Mobile optimization testing",
            "Device-specific analysis",
            "Responsive design validation"
        ]
    },
    
    "checkout_abandonment": {
        "name": "High Cart Abandonment",
        "description": "Many add-to-carts but low checkout completion",
        "base_sessions": 13000,
        "growth_rate": 0.03,
        "conversion_rate": 0.018,  # Low final conversion
        "bounce_rate": 0.40,
        "avg_order_value": 72.00,
        "cart_abandonment_rate": 0.75,  # 75% abandon cart
        "use_cases": [
            "Funnel analysis testing",
            "Abandonment recovery testing",
            "Payment flow optimization"
        ],
        "notes": "Suggests issues with shipping costs or payment options"
    },
    
    "new_product_launch": {
        "name": "Product Launch Spike",
        "description": "New product launch with high engagement but normal conversion",
        "base_sessions": 20000,
        "growth_rate": 0.15,  # 15% growth from launch
        "conversion_rate": 0.028,
        "bounce_rate": 0.35,  # Low bounce (high interest)
        "avg_order_value": 110.00,  # Higher AOV (premium product)
        "engagement_rate": 0.65,  # High engagement
        "use_cases": [
            "Launch monitoring",
            "Product interest tracking",
            "Pricing sensitivity testing"
        ]
    },
    
    "returning_visitors": {
        "name": "High Returning Visitor Rate",
        "description": "70% returning visitors with high conversion",
        "base_sessions": 14000,
        "growth_rate": 0.06,
        "conversion_rate": 0.042,  # High conversion from loyalty
        "bounce_rate": 0.32,  # Low bounce
        "avg_order_value": 88.00,
        "returning_visitor_rate": 0.70,  # 70% returning
        "use_cases": [
            "Retention analysis",
            "Loyalty program testing",
            "Repeat purchase patterns"
        ]
    }
}


def get_scenario(scenario_name: str) -> Dict[str, Any]:
    """
    Get scenario configuration by name.
    
    Args:
        scenario_name: Name of the scenario
        
    Returns:
        Scenario configuration dict
        
    Raises:
        KeyError: If scenario doesn't exist
    """
    if scenario_name not in SCENARIOS:
        available = ", ".join(SCENARIOS.keys())
        raise KeyError(
            f"Unknown scenario '{scenario_name}'. "
            f"Available scenarios: {available}"
        )
    
    return SCENARIOS[scenario_name]


def list_scenarios() -> List[Dict[str, str]]:
    """
    List all available scenarios with descriptions.
    
    Returns:
        List of scenario summaries
    """
    summaries = []
    for key, config in SCENARIOS.items():
        summaries.append({
            "key": key,
            "name": config["name"],
            "description": config["description"],
            "base_sessions": config["base_sessions"],
            "conversion_rate": f"{config['conversion_rate']:.1%}",
            "growth_rate": f"{config['growth_rate']:+.1%}"
        })
    
    return summaries


def get_scenario_for_testing(test_type: str) -> str:
    """
    Get recommended scenario for specific test type.
    
    Args:
        test_type: Type of test (e.g., "alerts", "load", "baseline")
        
    Returns:
        Scenario key
    """
    recommendations = {
        "alerts": "conversion_drop",
        "anomaly": "conversion_drop",
        "load": "traffic_spike",
        "scalability": "traffic_spike",
        "baseline": "steady_growth",
        "normal": "steady_growth",
        "performance": "high_performance",
        "optimization": "high_performance",
        "seasonal": "seasonal_low",
        "mobile": "mobile_vs_desktop",
        "funnel": "checkout_abandonment",
        "launch": "new_product_launch",
        "retention": "returning_visitors"
    }
    
    return recommendations.get(test_type.lower(), "steady_growth")

