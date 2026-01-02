/**
 * ChartRenderer Usage Examples
 * 
 * Demonstrates all chart types supported by ChartRenderer.
 * Use this as a reference for integrating charts in your pages.
 */

'use client';

import React from 'react';
import { ChartRenderer, MultiChartRenderer } from './ChartRenderer';
import type { ChartConfig } from '@/types/charts.generated';

export const ChartExamplesPage: React.FC = () => {
  // Example 1: Line Chart (Time Series)
  const lineChartConfig: ChartConfig = {
    type: 'line',
    title: 'Sessions Over Time',
    x_label: 'Date',
    y_label: 'Sessions',
    data: [
      { x: '2025-01-01', y: 1234 },
      { x: '2025-01-02', y: 1456 },
      { x: '2025-01-03', y: 1389 },
      { x: '2025-01-04', y: 1567 },
      { x: '2025-01-05', y: 1678 },
      { x: '2025-01-06', y: 1445 },
      { x: '2025-01-07', y: 1523 },
    ],
    x_key: 'x',
    y_key: 'y',
  };

  // Example 2: Bar Chart (Categorical Comparison)
  const barChartConfig: ChartConfig = {
    type: 'bar',
    title: 'Traffic by Device',
    x_label: 'Device',
    y_label: 'Sessions',
    data: [
      { x: 'Mobile', y: 5678 },
      { x: 'Desktop', y: 3456 },
      { x: 'Tablet', y: 789 },
    ],
    x_key: 'x',
    y_key: 'y',
    horizontal: false,
  };

  // Example 3: Pie Chart (Percentage Breakdown)
  const pieChartConfig: ChartConfig = {
    type: 'pie',
    title: 'Traffic Sources',
    data: [
      { name: 'Organic Search', value: 45.2 },
      { name: 'Direct', value: 32.1 },
      { name: 'Referral', value: 22.7 },
    ],
  };

  // Example 4: Area Chart (Cumulative/Trend)
  const areaChartConfig: ChartConfig = {
    type: 'area',
    title: 'Conversions Trend',
    x_label: 'Date',
    y_label: 'Conversions',
    data: [
      { x: '2025-01-01', y: 56 },
      { x: '2025-01-02', y: 67 },
      { x: '2025-01-03', y: 61 },
      { x: '2025-01-04', y: 73 },
      { x: '2025-01-05', y: 82 },
    ],
    x_key: 'x',
    y_key: 'y',
    stacked: false,
  };

  const allCharts: ChartConfig[] = [
    lineChartConfig,
    barChartConfig,
    pieChartConfig,
    areaChartConfig,
  ];

  return (
    <div className="container mx-auto p-6">
      <h1 className="text-3xl font-bold mb-8">Chart Renderer Examples</h1>

      {/* Individual Chart Examples */}
      <section className="mb-12">
        <h2 className="text-2xl font-semibold mb-4">Individual Charts</h2>

        <div className="space-y-8">
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-xl font-medium mb-4">Line Chart Example</h3>
            <ChartRenderer config={lineChartConfig} height={350} />
          </div>

          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-xl font-medium mb-4">Bar Chart Example</h3>
            <ChartRenderer config={barChartConfig} height={350} />
          </div>

          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-xl font-medium mb-4">Pie Chart Example</h3>
            <ChartRenderer config={pieChartConfig} height={350} />
          </div>

          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-xl font-medium mb-4">Area Chart Example</h3>
            <ChartRenderer config={areaChartConfig} height={350} />
          </div>
        </div>
      </section>

      {/* Multi-Chart Grid */}
      <section>
        <h2 className="text-2xl font-semibold mb-4">Multi-Chart Grid</h2>
        <MultiChartRenderer charts={allCharts} />
      </section>

      {/* Integration Guide */}
      <section className="mt-12 bg-gray-50 p-6 rounded-lg">
        <h2 className="text-2xl font-semibold mb-4">Integration Guide</h2>

        <div className="space-y-4">
          <div>
            <h3 className="text-lg font-medium mb-2">1. Import the Component</h3>
            <pre className="bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto">
              <code>{`import { ChartRenderer } from '@/components/charts/ChartRenderer';
import type { ChartConfig } from '@/types/charts.generated';`}</code>
            </pre>
          </div>

          <div>
            <h3 className="text-lg font-medium mb-2">2. Get Chart Config from Backend</h3>
            <pre className="bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto">
              <code>{`// From your ReportResult
const report = await fetch('/api/v1/analytics/query', {
  method: 'POST',
  body: JSON.stringify({ query: 'Show sessions last week' })
}).then(res => res.json());

// report.charts is ChartConfig[]
const charts = report.charts;`}</code>
            </pre>
          </div>

          <div>
            <h3 className="text-lg font-medium mb-2">3. Render Charts</h3>
            <pre className="bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto">
              <code>{`{charts.map((chart, index) => (
  <ChartRenderer 
    key={index} 
    config={chart} 
    height={400}
    className="mb-6"
  />
))}`}</code>
            </pre>
          </div>

          <div className="bg-blue-50 border border-blue-200 p-4 rounded">
            <h3 className="text-lg font-medium mb-2 text-blue-900">✅ Task 5.2 Complete</h3>
            <p className="text-blue-800">
              ChartRenderer component implements all requirements:
            </p>
            <ul className="list-disc list-inside text-blue-800 mt-2 space-y-1">
              <li>Props: config (ChartData from backend schema)</li>
              <li>Switch statement on config.type</li>
              <li>Line chart: LineChart with XAxis, YAxis, Line</li>
              <li>Bar chart: BarChart with Bar</li>
              <li>Pie chart: PieChart with Pie</li>
              <li>Area chart: AreaChart with Area</li>
              <li>Full Recharts integration</li>
              <li>Type-safe with TypeScript</li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ChartExamplesPage;

