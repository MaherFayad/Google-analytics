/**
 * GA4 Analytics Dashboard Page
 * 
 * Implements Task 10.2: GA4 Analytics Dashboard Component [HIGH]
 * 
 * Features:
 * - Natural language query input
 * - Descriptive analytics (charts, metrics)
 * - Predictive analytics (pattern matching)
 * - Real-time streaming support
 * - Confidence-aware results
 * 
 * Usage:
 *   Navigate to /analytics
 */

'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { TypeSafeChartRenderer, ChartGrid } from '@/components/charts/TypeSafeChartRenderer';
import { MetricCard } from '@/components/ga4/MetricCard';
import { PatternCard } from '@/components/ga4/PatternCard';
import { QueryInput } from '@/components/ga4/QueryInput';
import { AnalyticsHeader } from '@/components/ga4/AnalyticsHeader';
import { ConfidenceBadge } from '@/components/ga4/ConfidenceBadge';
import type { ChartConfig } from '@/types/charts.generated';

interface AnalyticsResponse {
  answer: string;
  charts: ChartConfig[];
  metrics: Array<{
    label: string;
    value: string;
    change?: string;
    trend?: 'up' | 'down' | 'neutral';
  }>;
  patterns?: Array<{
    description: string;
    similarity_score: float;
    date_range: string;
    metric_values: Record<string, any>;
  }>;
  confidence: number;
  status: 'high_confidence' | 'medium_confidence' | 'low_confidence' | 'no_relevant_context';
  citations?: Array<{
    metric_id: number;
    property_id: string;
    metric_date: string;
    similarity_score: number;
  }>;
  timestamp: string;
}

export default function GA4AnalyticsPage() {
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Fetch analytics data
  const { data: analyticsData, error, refetch } = useQuery<AnalyticsResponse>({
    queryKey: ['analytics', submittedQuery],
    queryFn: async () => {
      if (!submittedQuery) throw new Error('No query provided');
      
      const response = await axios.post('/api/v1/analytics/query', {
        query: submittedQuery,
        property_id: 'default', // TODO: Get from tenant context
      });
      
      return response.data;
    },
    enabled: !!submittedQuery,
  });

  const handleSubmit = (newQuery: string) => {
    setSubmittedQuery(newQuery);
    setIsLoading(true);
    refetch().finally(() => setIsLoading(false));
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <AnalyticsHeader />

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Query Input Section */}
        <div className="mb-8">
          <QueryInput
            value={query}
            onChange={setQuery}
            onSubmit={handleSubmit}
            isLoading={isLoading}
            placeholder="Ask me about your GA4 data... (e.g., 'Show mobile conversions last week')"
          />
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            <span className="ml-4 text-gray-600">Analyzing your data...</span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <h3 className="text-red-800 font-semibold mb-2">Error</h3>
            <p className="text-red-600">{(error as Error).message}</p>
          </div>
        )}

        {/* Results */}
        {analyticsData && !isLoading && (
          <div className="space-y-8">
            {/* Confidence Badge */}
            <ConfidenceBadge
              confidence={analyticsData.confidence}
              status={analyticsData.status}
            />

            {/* Answer Summary */}
            <div className="bg-white rounded-lg shadow-sm p-6">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">Analysis</h2>
              <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                {analyticsData.answer}
              </p>
            </div>

            {/* Metrics Section */}
            {analyticsData.metrics && analyticsData.metrics.length > 0 && (
              <div>
                <h2 className="text-xl font-semibold text-gray-900 mb-4">Key Metrics</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {analyticsData.metrics.map((metric, index) => (
                    <MetricCard key={index} metric={metric} />
                  ))}
                </div>
              </div>
            )}

            {/* Charts Section (Descriptive) */}
            {analyticsData.charts && analyticsData.charts.length > 0 && (
              <div>
                <h2 className="text-xl font-semibold text-gray-900 mb-4">
                  Visualizations
                </h2>
                <ChartGrid charts={analyticsData.charts} />
              </div>
            )}

            {/* Patterns Section (Predictive) */}
            {analyticsData.patterns && analyticsData.patterns.length > 0 && (
              <div>
                <h2 className="text-xl font-semibold text-gray-900 mb-4">
                  Historical Patterns
                  <span className="ml-2 text-sm font-normal text-gray-500">
                    (Similar trends from your history)
                  </span>
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {analyticsData.patterns.map((pattern, index) => (
                    <PatternCard key={index} pattern={pattern} />
                  ))}
                </div>
              </div>
            )}

            {/* Citations Section */}
            {analyticsData.citations && analyticsData.citations.length > 0 && (
              <details className="bg-gray-50 rounded-lg p-4">
                <summary className="cursor-pointer text-sm font-medium text-gray-700">
                  Data Sources ({analyticsData.citations.length})
                </summary>
                <div className="mt-4 space-y-2">
                  {analyticsData.citations.map((citation, index) => (
                    <div
                      key={index}
                      className="text-xs text-gray-600 bg-white p-2 rounded border border-gray-200"
                    >
                      <span className="font-mono">
                        Property: {citation.property_id} | Date: {citation.metric_date} | 
                        Confidence: {(citation.similarity_score * 100).toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}

        {/* Empty State */}
        {!analyticsData && !isLoading && !error && (
          <div className="text-center py-12">
            <div className="mx-auto w-24 h-24 bg-blue-100 rounded-full flex items-center justify-center mb-4">
              <svg
                className="w-12 h-12 text-blue-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Ask About Your Analytics
            </h3>
            <p className="text-gray-600 max-w-md mx-auto">
              Use natural language to query your GA4 data. For example, "Show mobile conversions last week" or "Compare desktop vs mobile traffic".
            </p>
          </div>
        )}
      </main>
    </div>
  );
}

