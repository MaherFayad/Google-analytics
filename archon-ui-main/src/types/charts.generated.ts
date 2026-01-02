/**
 * Chart Type Definitions (Placeholder)
 * 
 * This file will be auto-generated from backend Pydantic schemas.
 * 
 * To generate types:
 *   1. Start the backend server: cd ../python && uvicorn src.server.main:app --reload
 *   2. Run type generation: npm run generate:types
 * 
 * DO NOT EDIT MANUALLY - Changes will be overwritten
 */

// Placeholder types until generation is run
export type ChartDataPoint = {
  x: string | number;
  y: number;
};

export type PieChartDataPoint = {
  name: string;
  value: number;
};

export type LineChartConfig = {
  type: 'line';
  title: string;
  x_label: string;
  y_label: string;
  data: ChartDataPoint[];
  x_key?: string;
  y_key?: string;
};

export type BarChartConfig = {
  type: 'bar';
  title: string;
  x_label: string;
  y_label: string;
  data: ChartDataPoint[];
  x_key?: string;
  y_key?: string;
  horizontal?: boolean;
};

export type PieChartConfig = {
  type: 'pie';
  title: string;
  data: PieChartDataPoint[];
};

export type AreaChartConfig = {
  type: 'area';
  title: string;
  x_label: string;
  y_label: string;
  data: ChartDataPoint[];
  x_key?: string;
  y_key?: string;
  stacked?: boolean;
};

export type ChartConfig =
  | LineChartConfig
  | BarChartConfig
  | PieChartConfig
  | AreaChartConfig;

export type MetricCard = {
  label: string;
  value: string;
  change?: string | null;
  trend?: 'up' | 'down' | 'neutral' | null;
};

// Type guards
export function isLineChart(config: ChartConfig): config is LineChartConfig {
  return config.type === 'line';
}

export function isBarChart(config: ChartConfig): config is BarChartConfig {
  return config.type === 'bar';
}

export function isPieChart(config: ChartConfig): config is PieChartConfig {
  return config.type === 'pie';
}

export function isAreaChart(config: ChartConfig): config is AreaChartConfig {
  return config.type === 'area';
}

export function getChartType(config: ChartConfig): 'line' | 'bar' | 'pie' | 'area' {
  return config.type;
}

