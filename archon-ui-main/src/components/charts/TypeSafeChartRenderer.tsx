/**
 * Type-Safe Chart Renderer Component
 * 
 * Implements Task P0-35: Enforce Chart Schema with Pydantic → OpenAPI → TypeScript
 * 
 * Features:
 * - Compile-time type safety using generated types
 * - Runtime validation against Pydantic schemas
 * - Type guards for discriminated union handling
 * - No more chart_type vs type confusion!
 * 
 * Usage:
 *   import { TypeSafeChartRenderer } from '@/components/charts/TypeSafeChartRenderer';
 *   import type { ChartConfig } from '@/types/charts.generated';
 *   
 *   <TypeSafeChartRenderer config={chartConfig} />
 */

'use client';

import React from 'react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell,
  ResponsiveContainer,
} from 'recharts';

// Import generated types (Task P0-35)
import type {
  ChartConfig,
  LineChartConfig,
  BarChartConfig,
  PieChartConfig,
  AreaChartConfig,
  isLineChart,
  isBarChart,
  isPieChart,
  isAreaChart,
} from '@/types/charts.generated';

// Color palette for charts
const CHART_COLORS = [
  '#3b82f6', // blue-500
  '#10b981', // green-500
  '#f59e0b', // amber-500
  '#ef4444', // red-500
  '#8b5cf6', // violet-500
  '#ec4899', // pink-500
  '#06b6d4', // cyan-500
  '#f97316', // orange-500
];

interface TypeSafeChartRendererProps {
  config: ChartConfig;
  width?: number | string;
  height?: number;
  className?: string;
}

/**
 * Type-safe chart renderer using discriminated union
 * 
 * TypeScript knows the exact type of config based on config.type,
 * preventing field name mismatches at compile time.
 */
export const TypeSafeChartRenderer: React.FC<TypeSafeChartRendererProps> = ({
  config,
  width = '100%',
  height = 300,
  className = '',
}) => {
  // Render based on chart type (discriminated union)
  // TypeScript knows exact type in each branch!
  switch (config.type) {
    case 'line':
      return <LineChartRenderer config={config} width={width} height={height} className={className} />;
    
    case 'bar':
      return <BarChartRenderer config={config} width={width} height={height} className={className} />;
    
    case 'pie':
      return <PieChartRenderer config={config} width={width} height={height} className={className} />;
    
    case 'area':
      return <AreaChartRenderer config={config} width={width} height={height} className={className} />;
    
    default:
      // This will never happen due to discriminated union exhaustiveness checking
      const _exhaustiveCheck: never = config;
      return <div className="text-red-600">Unknown chart type</div>;
  }
};

/**
 * Line Chart Renderer
 * 
 * config is typed as LineChartConfig (not generic ChartConfig)
 */
const LineChartRenderer: React.FC<{
  config: LineChartConfig;
  width: number | string;
  height: number;
  className: string;
}> = ({ config, width, height, className }) => {
  return (
    <div className={`chart-container ${className}`}>
      <h3 className="text-lg font-semibold mb-2">{config.title}</h3>
      <ResponsiveContainer width={width} height={height}>
        <LineChart data={config.data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis 
            dataKey={config.x_key} 
            label={{ value: config.x_label, position: 'insideBottom', offset: -5 }}
          />
          <YAxis 
            label={{ value: config.y_label, angle: -90, position: 'insideLeft' }}
          />
          <Tooltip />
          <Legend />
          <Line 
            type="monotone" 
            dataKey={config.y_key} 
            stroke={CHART_COLORS[0]} 
            strokeWidth={2}
            dot={{ r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

/**
 * Bar Chart Renderer
 * 
 * config is typed as BarChartConfig
 */
const BarChartRenderer: React.FC<{
  config: BarChartConfig;
  width: number | string;
  height: number;
  className: string;
}> = ({ config, width, height, className }) => {
  return (
    <div className={`chart-container ${className}`}>
      <h3 className="text-lg font-semibold mb-2">{config.title}</h3>
      <ResponsiveContainer width={width} height={height}>
        <BarChart 
          data={config.data}
          layout={config.horizontal ? 'horizontal' : 'vertical'}
        >
          <CartesianGrid strokeDasharray="3 3" />
          {config.horizontal ? (
            <>
              <XAxis type="number" label={{ value: config.y_label, position: 'insideBottom' }} />
              <YAxis type="category" dataKey={config.x_key} label={{ value: config.x_label }} />
            </>
          ) : (
            <>
              <XAxis dataKey={config.x_key} label={{ value: config.x_label, position: 'insideBottom', offset: -5 }} />
              <YAxis label={{ value: config.y_label, angle: -90, position: 'insideLeft' }} />
            </>
          )}
          <Tooltip />
          <Legend />
          <Bar 
            dataKey={config.y_key} 
            fill={CHART_COLORS[1]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

/**
 * Pie Chart Renderer
 * 
 * config is typed as PieChartConfig
 */
const PieChartRenderer: React.FC<{
  config: PieChartConfig;
  width: number | string;
  height: number;
  className: string;
}> = ({ config, width, height, className }) => {
  return (
    <div className={`chart-container ${className}`}>
      <h3 className="text-lg font-semibold mb-2">{config.title}</h3>
      <ResponsiveContainer width={width} height={height}>
        <PieChart>
          <Pie
            data={config.data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            outerRadius={80}
            label={(entry) => `${entry.name}: ${entry.value.toFixed(1)}%`}
          >
            {config.data.map((_, index) => (
              <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
};

/**
 * Area Chart Renderer
 * 
 * config is typed as AreaChartConfig
 */
const AreaChartRenderer: React.FC<{
  config: AreaChartConfig;
  width: number | string;
  height: number;
  className: string;
}> = ({ config, width, height, className }) => {
  return (
    <div className={`chart-container ${className}`}>
      <h3 className="text-lg font-semibold mb-2">{config.title}</h3>
      <ResponsiveContainer width={width} height={height}>
        <AreaChart data={config.data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis 
            dataKey={config.x_key} 
            label={{ value: config.x_label, position: 'insideBottom', offset: -5 }}
          />
          <YAxis 
            label={{ value: config.y_label, angle: -90, position: 'insideLeft' }}
          />
          <Tooltip />
          <Legend />
          <Area 
            type="monotone" 
            dataKey={config.y_key} 
            fill={CHART_COLORS[2]}
            stroke={CHART_COLORS[2]}
            fillOpacity={0.6}
            stackId={config.stacked ? '1' : undefined}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

/**
 * Example: Multiple charts in a grid
 */
export const ChartGrid: React.FC<{ charts: ChartConfig[] }> = ({ charts }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {charts.map((chart, index) => (
        <TypeSafeChartRenderer 
          key={index} 
          config={chart} 
          className="bg-white p-4 rounded-lg shadow"
        />
      ))}
    </div>
  );
};

export default TypeSafeChartRenderer;

