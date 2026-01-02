"""
ReportingAgent - Generates structured reports with charts.

Implements Task P0-1: ReportingAgent

Responsibilities:
- Generate natural language insights
- Create chart configurations for Recharts
- Produce metric cards with trends
- Include source citations for transparency
"""

import logging
from typing import Any, Dict, List

from pydantic_ai import Agent, RunContext

from .base_agent import BaseAgent
from .schemas.results import (
    ReportResult,
    ChartConfig,
    ChartDataPoint,
    MetricCard,
    SourceCitation,
)

logger = logging.getLogger(__name__)


class ReportingAgent(BaseAgent[ReportResult]):
    """
    Agent for generating structured reports.
    
    Implements Task P0-1: ReportingAgent
    
    Features:
    - Natural language insights generation
    - Chart configuration for Recharts
    - Metric cards with period-over-period comparison
    - Source citation for data provenance
    
    Contract:
        ReportingAgent.generate() → ReportResult(answer, charts, metrics)
    """
    
    def __init__(self, openai_api_key: str):
        """
        Initialize Reporting agent.
        
        Args:
            openai_api_key: OpenAI API key for LLM
        """
        super().__init__(
            name="reporting",
            model="openai:gpt-4o",
            retries=2,
            timeout_seconds=20,
        )
        self.api_key = openai_api_key
        
        # Create Pydantic-AI agent for report generation
        self._pydantic_agent = Agent(
            model=self.model,
            system_prompt=self.get_system_prompt(),
        )
    
    def get_system_prompt(self) -> str:
        """System prompt for Reporting agent."""
        return """You are an expert data analyst specializing in Google Analytics 4 reporting.

Your job is to:
1. Analyze GA4 metrics and trends
2. Generate clear, actionable insights
3. Create chart configurations for data visualization
4. Present findings in a structured format

Guidelines:
- Be concise and business-focused
- Highlight trends and anomalies
- Suggest actionable recommendations
- Use data visualization when helpful
- Always cite your sources

Output format:
- Natural language answer (2-3 paragraphs)
- Chart configurations (JSON for Recharts)
- Key metric cards with period-over-period changes
"""
    
    async def run_async(
        self,
        ctx: RunContext,
        query: str,
        ga4_data: Dict[str, Any],
        retrieved_context: List[str],
        citations: List[SourceCitation],
        tenant_id: str,
        **kwargs: Any
    ) -> ReportResult:
        """
        Generate structured report from GA4 data and context.
        
        Args:
            ctx: Run context
            query: User's original query
            ga4_data: Fresh GA4 data from DataFetcherAgent
            retrieved_context: Historical context from RagAgent
            citations: Source citations for provenance
            tenant_id: Tenant ID
            
        Returns:
            ReportResult with answer, charts, and metrics
        """
        try:
            logger.info(f"Generating report for query: {query}")
            
            # Extract metrics from GA4 data
            metrics_summary = self._extract_metrics(ga4_data)
            
            # Generate natural language answer
            answer = self._generate_answer(
                query=query,
                metrics=metrics_summary,
                context=retrieved_context,
            )
            
            # Create chart configurations
            charts = self._create_charts(ga4_data)
            
            # Create metric cards
            metric_cards = self._create_metric_cards(ga4_data)
            
            # Calculate confidence based on data quality
            confidence = self._calculate_confidence(
                ga4_data=ga4_data,
                context=retrieved_context,
            )
            
            logger.info(
                f"Report generated (confidence: {confidence:.2f})",
                extra={
                    "charts": len(charts),
                    "metrics": len(metric_cards),
                    "citations": len(citations)
                }
            )
            
            return ReportResult(
                answer=answer,
                charts=charts,
                metrics=metric_cards,
                citations=citations,
                confidence=confidence,
                tenant_id=tenant_id,
                query=query,
            )
            
        except Exception as e:
            logger.error(f"Report generation failed: {e}", exc_info=True)
            
            # Return fallback report
            return ReportResult(
                answer=f"I encountered an error generating the report: {str(e)}",
                charts=[],
                metrics=[],
                citations=citations,
                confidence=0.0,
                tenant_id=tenant_id,
                query=query,
            )
    
    def _extract_metrics(self, ga4_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metrics summary from GA4 data."""
        rows = ga4_data.get("rows", [])
        
        if not rows:
            return {}
        
        # Extract metric values from first row (simplified)
        metrics = {}
        metric_headers = ga4_data.get("metricHeaders", [])
        
        for idx, header in enumerate(metric_headers):
            metric_name = header.get("name", f"metric_{idx}")
            if rows and idx < len(rows[0].get("metricValues", [])):
                metrics[metric_name] = rows[0]["metricValues"][idx].get("value", "0")
        
        return metrics
    
    def _generate_answer(
        self,
        query: str,
        metrics: Dict[str, Any],
        context: List[str],
    ) -> str:
        """Generate natural language answer."""
        # Simplified answer generation
        # In production, this would use the LLM
        
        if not metrics:
            return "I don't have enough data to answer your query. Please ensure GA4 data is available."
        
        # Build answer from metrics and context
        answer_parts = [
            f"Based on your GA4 data, here's what I found:",
        ]
        
        # Add metrics
        for metric_name, value in metrics.items():
            answer_parts.append(f"- {metric_name}: {value}")
        
        # Add historical context
        if context:
            answer_parts.append("\nHistorical context:")
            for ctx in context[:2]:  # Limit to top 2
                answer_parts.append(f"- {ctx}")
        
        return "\n".join(answer_parts)
    
    def _create_charts(self, ga4_data: Dict[str, Any]) -> List[ChartConfig]:
        """Create chart configurations from GA4 data."""
        charts = []
        rows = ga4_data.get("rows", [])
        
        if not rows:
            return charts
        
        # Create line chart for time-series data
        dimension_headers = ga4_data.get("dimensionHeaders", [])
        metric_headers = ga4_data.get("metricHeaders", [])
        
        if dimension_headers and metric_headers:
            # Extract data points
            data_points = []
            for row in rows[:30]:  # Limit to 30 data points
                dim_values = row.get("dimensionValues", [])
                metric_values = row.get("metricValues", [])
                
                if dim_values and metric_values:
                    data_points.append(
                        ChartDataPoint(
                            x=dim_values[0].get("value", ""),
                            y=float(metric_values[0].get("value", 0)),
                        )
                    )
            
            if data_points:
                charts.append(
                    ChartConfig(
                        type="line",
                        title=f"{metric_headers[0].get('name', 'Metric')} Over Time",
                        x_label=dimension_headers[0].get("name", "Date"),
                        y_label=metric_headers[0].get("name", "Value"),
                        data=data_points,
                    )
                )
        
        return charts
    
    def _create_metric_cards(self, ga4_data: Dict[str, Any]) -> List[MetricCard]:
        """Create metric cards from GA4 data."""
        cards = []
        rows = ga4_data.get("rows", [])
        metric_headers = ga4_data.get("metricHeaders", [])
        
        if not rows or not metric_headers:
            return cards
        
        # Create cards for each metric
        for idx, header in enumerate(metric_headers[:4]):  # Limit to 4 cards
            metric_name = header.get("name", f"Metric {idx}")
            
            if rows and idx < len(rows[0].get("metricValues", [])):
                value = rows[0]["metricValues"][idx].get("value", "0")
                
                # Format value
                try:
                    num_value = float(value)
                    formatted_value = f"{num_value:,.0f}" if num_value >= 1 else f"{num_value:.2f}"
                except:
                    formatted_value = value
                
                cards.append(
                    MetricCard(
                        label=metric_name.replace("_", " ").title(),
                        value=formatted_value,
                        change=None,  # TODO: Calculate from period comparison
                        trend=None,
                    )
                )
        
        return cards
    
    def _calculate_confidence(
        self,
        ga4_data: Dict[str, Any],
        context: List[str],
    ) -> float:
        """Calculate report confidence score."""
        confidence = 0.5  # Base confidence
        
        # Increase confidence if we have fresh GA4 data
        if ga4_data.get("rows"):
            confidence += 0.3
        
        # Increase confidence if we have historical context
        if context:
            confidence += 0.2
        
        return min(1.0, confidence)

