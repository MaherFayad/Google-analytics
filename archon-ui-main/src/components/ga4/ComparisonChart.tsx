/**
 * Comparison Chart Component
 * 
 * Implements Task P0-8: Period-over-Period Comparison Visualization
 * 
 * Features:
 * - Overlay two time periods on same chart
 * - Show percentage changes
 * - Support multiple metrics
 * - Highlight significant changes
 * 
 * Usage:
 *   <ComparisonChart
 *     currentData={[...]}
 *     previousData={[...]}
 *     metricName="Sessions"
 *   />
 */

'use client';

import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

export interface ComparisonDataPoint {
  date: string;
  current: number;
  previous: number;
  change?: number; // Percentage change
}

export interface ComparisonChartProps {
  data: ComparisonDataPoint[];
  title: string;
  metricName?: string;
  currentLabel?: string;
  previousLabel?: string;
  width?: number | string;
  height?: number;
  className?: string;
}

export const ComparisonChart: React.FC<ComparisonChartProps> = ({
  data,
  title,
  metricName = 'Metric',
  currentLabel = 'Current Period',
  previousLabel = 'Previous Period',
  width = '100%',
  height = 400,
  className = '',
}) => {
  // Calculate summary statistics
  const currentTotal = data.reduce((sum, point) => sum + point.current, 0);
  const previousTotal = data.reduce((sum, point) => sum + point.previous, 0);
  const overallChange = previousTotal > 0
    ? ((currentTotal - previousTotal) / previousTotal) * 100
    : 0;

  return (
    <div className={`comparison-chart-container ${className}`}>
      {/* Header with summary */}
      <div className="mb-4">
        <h3 className="text-lg font-semibold">{title}</h3>
        <div className="flex items-center gap-4 mt-2">
          <div className="text-sm">
            <span className="text-gray-600">Current: </span>
            <span className="font-medium">{currentTotal.toLocaleString()}</span>
          </div>
          <div className="text-sm">
            <span className="text-gray-600">Previous: </span>
            <span className="font-medium">{previousTotal.toLocaleString()}</span>
          </div>
          <div className={`text-sm font-medium ${
            overallChange > 0 ? 'text-green-600' : 'text-red-600'
          }`}>
            {overallChange > 0 ? '+' : ''}{overallChange.toFixed(1)}%
          </div>
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width={width} height={height}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            label={{ value: 'Date', position: 'insideBottom', offset: -5 }}
          />
          <YAxis
            label={{ value: metricName, angle: -90, position: 'insideLeft' }}
          />
          <Tooltip content={<CustomTooltip metricName={metricName} />} />
          <Legend />
          <Line
            type="monotone"
            dataKey="current"
            name={currentLabel}
            stroke="#3b82f6" // blue-500
            strokeWidth={2}
            dot={{ r: 4 }}
            activeDot={{ r: 6 }}
          />
          <Line
            type="monotone"
            dataKey="previous"
            name={previousLabel}
            stroke="#94a3b8" // slate-400
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>

      {/* Period Comparison Table */}
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left py-2 px-4">Date</th>
              <th className="text-right py-2 px-4">{currentLabel}</th>
              <th className="text-right py-2 px-4">{previousLabel}</th>
              <th className="text-right py-2 px-4">Change</th>
            </tr>
          </thead>
          <tbody>
            {data.map((point, index) => {
              const change = point.previous > 0
                ? ((point.current - point.previous) / point.previous) * 100
                : 0;
              
              return (
                <tr key={index} className="border-b hover:bg-gray-50">
                  <td className="py-2 px-4">{point.date}</td>
                  <td className="text-right py-2 px-4 font-medium">
                    {point.current.toLocaleString()}
                  </td>
                  <td className="text-right py-2 px-4 text-gray-600">
                    {point.previous.toLocaleString()}
                  </td>
                  <td className={`text-right py-2 px-4 font-medium ${
                    change > 0 ? 'text-green-600' : change < 0 ? 'text-red-600' : 'text-gray-600'
                  }`}>
                    {change > 0 ? '+' : ''}{change.toFixed(1)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

/**
 * Custom tooltip showing comparison details
 */
const CustomTooltip: React.FC<{
  active?: boolean;
  payload?: any[];
  label?: string;
  metricName: string;
}> = ({ active, payload, label, metricName }) => {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const current = payload.find(p => p.dataKey === 'current')?.value || 0;
  const previous = payload.find(p => p.dataKey === 'previous')?.value || 0;
  const change = previous > 0 ? ((current - previous) / previous) * 100 : 0;

  return (
    <div className="bg-white p-3 border border-gray-200 rounded shadow-lg">
      <p className="font-medium mb-2">{label}</p>
      <div className="space-y-1 text-sm">
        <div className="flex justify-between gap-4">
          <span className="text-blue-600">Current:</span>
          <span className="font-medium">{current.toLocaleString()}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-gray-600">Previous:</span>
          <span>{previous.toLocaleString()}</span>
        </div>
        <div className="flex justify-between gap-4 pt-1 border-t">
          <span className="text-gray-600">Change:</span>
          <span className={`font-medium ${
            change > 0 ? 'text-green-600' : change < 0 ? 'text-red-600' : 'text-gray-600'
          }`}>
            {change > 0 ? '+' : ''}{change.toFixed(1)}%
          </span>
        </div>
      </div>
    </div>
  );
};

/**
 * Helper: Transform raw data into comparison format
 * 
 * Example:
 *   const comparisonData = transformToComparisonData(
 *     currentPeriodData,  // [{date: '2025-01-01', value: 1234}, ...]
 *     previousPeriodData, // [{date: '2024-12-25', value: 1000}, ...]
 *   );
 */
export function transformToComparisonData(
  currentData: Array<{ date: string; value: number }>,
  previousData: Array<{ date: string; value: number }>,
): ComparisonDataPoint[] {
  // Align dates (current dates, map to corresponding previous)
  return currentData.map((currentPoint, index) => ({
    date: currentPoint.date,
    current: currentPoint.value,
    previous: previousData[index]?.value || 0,
  }));
}

export default ComparisonChart;

