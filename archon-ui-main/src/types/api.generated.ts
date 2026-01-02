/**
 * API Type Definitions (Placeholder)
 * 
 * This file will be auto-generated from the backend OpenAPI schema.
 * 
 * To generate types:
 *   1. Start the backend server: cd ../python && uvicorn src.server.main:app --reload
 *   2. Run type generation: npm run generate:types
 * 
 * DO NOT EDIT MANUALLY - Changes will be overwritten
 */

// Placeholder until generation is run
export interface components {
  schemas: {
    ChartDataPoint: {
      x: string | number;
      y: number;
    };
    PieChartDataPoint: {
      name: string;
      value: number;
    };
    LineChartConfig: {
      type: 'line';
      title: string;
      x_label: string;
      y_label: string;
      data: components['schemas']['ChartDataPoint'][];
      x_key?: string;
      y_key?: string;
    };
    BarChartConfig: {
      type: 'bar';
      title: string;
      x_label: string;
      y_label: string;
      data: components['schemas']['ChartDataPoint'][];
      x_key?: string;
      y_key?: string;
      horizontal?: boolean;
    };
    PieChartConfig: {
      type: 'pie';
      title: string;
      data: components['schemas']['PieChartDataPoint'][];
    };
    AreaChartConfig: {
      type: 'area';
      title: string;
      x_label: string;
      y_label: string;
      data: components['schemas']['ChartDataPoint'][];
      x_key?: string;
      y_key?: string;
      stacked?: boolean;
    };
    MetricCard: {
      label: string;
      value: string;
      change?: string | null;
      trend?: 'up' | 'down' | 'neutral' | null;
    };
  };
}

