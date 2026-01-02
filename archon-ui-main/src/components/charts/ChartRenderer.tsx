/**
 * ChartRenderer Component
 * 
 * Implements Task 5.2: Dynamic Chart Components
 * 
 * Simple, clean interface for rendering dynamic charts from backend schema.
 * Uses Recharts for visualization with full type safety.
 * 
 * Usage:
 *   import { ChartRenderer } from '@/components/charts/ChartRenderer';
 *   
 *   <ChartRenderer config={chartConfig} />
 * 
 * Props:
 *   - config: ChartConfig (from backend schema)
 *     - type: 'line' | 'bar' | 'pie' | 'area'
 *     - title: string
 *     - data: ChartDataPoint[]
 *     - x_key, y_key: string (for line/bar/area)
 * 
 * Tech: Recharts, React, TypeScript
 */

'use client';

import React from 'react';
import {
  TypeSafeChartRenderer,
  ChartGrid,
} from './TypeSafeChartRenderer';
import type { ChartConfig } from '@/types/charts.generated';

// Simple props interface
export interface ChartRendererProps {
  config: ChartConfig;
  width?: number | string;
  height?: number;
  className?: string;
}

/**
 * ChartRenderer - Dynamic chart component with switch statement logic
 * 
 * Implements Task 5.2: Switch statement on config.type
 * - Case 'line': Render <LineChart> with <XAxis>, <Line>
 * - Case 'bar': Render <BarChart> with <Bar>
 * - Case 'pie': Render <PieChart> with <Pie>
 * - Case 'area': Render <AreaChart> with <Area>
 * 
 * This is a thin wrapper around TypeSafeChartRenderer that provides
 * the exact interface requested in Task 5.2.
 */
export const ChartRenderer: React.FC<ChartRendererProps> = ({
  config,
  width = '100%',
  height = 300,
  className = '',
}) => {
  return (
    <TypeSafeChartRenderer
      config={config}
      width={width}
      height={height}
      className={className}
    />
  );
};

/**
 * Helper component for rendering multiple charts in a grid layout
 */
export const MultiChartRenderer: React.FC<{ charts: ChartConfig[] }> = ({
  charts,
}) => {
  return <ChartGrid charts={charts} />;
};

// Default export
export default ChartRenderer;

/**
 * Example Usage:
 * 
 * const lineChartConfig = {
 *   type: 'line',
 *   title: 'Sessions Over Time',
 *   x_label: 'Date',
 *   y_label: 'Sessions',
 *   data: [
 *     { x: '2025-01-01', y: 1234 },
 *     { x: '2025-01-02', y: 1456 },
 *     { x: '2025-01-03', y: 1389 },
 *   ],
 *   x_key: 'x',
 *   y_key: 'y',
 * };
 * 
 * <ChartRenderer config={lineChartConfig} />
 * 
 * 
 * const barChartConfig = {
 *   type: 'bar',
 *   title: 'Traffic by Device',
 *   x_label: 'Device',
 *   y_label: 'Sessions',
 *   data: [
 *     { x: 'Mobile', y: 5678 },
 *     { x: 'Desktop', y: 3456 },
 *     { x: 'Tablet', y: 789 },
 *   ],
 *   horizontal: false,
 * };
 * 
 * <ChartRenderer config={barChartConfig} />
 */

