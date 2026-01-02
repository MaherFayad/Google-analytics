# GA4 API Response Fixtures

This directory contains JSON fixtures for testing GA4 API integration.

## Files

- `page_views_weekly.json` - Weekly page view metrics
- `conversions_daily.json` - Daily conversion metrics
- `events_sample.json` - Event tracking data
- `steady_growth_7days.json` - Steady growth scenario
- `conversion_drop_7days.json` - Conversion drop alert scenario

## Usage

```python
import json
from pathlib import Path

# Load fixture
fixture_path = Path(__file__).parent / "fixtures" / "ga4_responses" / "page_views_weekly.json"
with open(fixture_path) as f:
    mock_response = json.load(f)

# Use in tests
@pytest.fixture
def ga4_page_views_response():
    fixture_path = Path(__file__).parent.parent / "fixtures" / "ga4_responses" / "page_views_weekly.json"
    with open(fixture_path) as f:
        return json.load(f)
```

## Generating Fixtures

Use the mock service to generate fixtures:

```python
from server.services.ga4 import GA4MockService
from uuid import UUID
import json

# Generate fixture
mock = GA4MockService(
    property_id="123456789",
    tenant_id=UUID("..."),
    scenario="steady_growth"
)

response = await mock.fetch_page_views(
    start_date="2025-01-01",
    end_date="2025-01-07"
)

# Save as fixture
with open("steady_growth_7days.json", "w") as f:
    json.dump(response, f, indent=2)
```

