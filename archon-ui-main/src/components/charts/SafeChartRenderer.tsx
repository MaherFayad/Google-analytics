/**
 * Safe Chart Renderer with Error Boundary
 * 
 * Implements Task 6.2: Global Error Boundary Integration
 * 
 * Wraps ChartRenderer with ChartErrorBoundary for graceful error handling.
 * Use this component in production to ensure charts never crash the UI.
 * 
 * Usage:
 *   import { SafeChartRenderer } from '@/components/charts/SafeChartRenderer';
 *   
 *   <SafeChartRenderer config={chartConfig} />
 */

'use client';

import React from 'react';
import { ChartRenderer, ChartRendererProps } from './ChartRenderer';
import { ChartErrorBoundary } from '@/components/errors';

export interface SafeChartRendererProps extends ChartRendererProps {
  onError?: (error: Error) => void;
}

/**
 * ChartRenderer wrapped with error boundary
 * 
 * Benefits:
 * - Catches malformed chart data errors
 * - Shows fallback UI with raw data table
 * - Allows data download as JSON
 * - Doesn't crash parent components
 */
export const SafeChartRenderer: React.FC<SafeChartRendererProps> = ({
  config,
  width,
  height,
  className,
  onError,
}) => {
  return (
    <ChartErrorBoundary
      chartData={config}
      chartTitle={config?.title}
      onError={onError}
    >
      <ChartRenderer
        config={config}
        width={width}
        height={height}
        className={className}
      />
    </ChartErrorBoundary>
  );
};

export default SafeChartRenderer;

