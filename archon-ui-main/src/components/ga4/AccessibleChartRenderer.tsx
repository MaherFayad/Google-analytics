/**
 * Accessible Chart Renderer
 * 
 * Implements Task P0-37: Chart Accessibility (WCAG 2.1 AA Compliance)
 * 
 * Features:
 * - WCAG 2.1 AA compliant (4.5:1 contrast ratio)
 * - Colorblind-safe palettes
 * - Keyboard navigation (Arrow keys, Home/End, Enter, Escape)
 * - Screen reader support (ARIA labels, live regions)
 * - Focus indicators
 * - Text alternatives for all visual information
 * 
 * Usage:
 *   <AccessibleChartRenderer
 *     config={chartConfig}
 *     title="Monthly Sales Trend"
 *     description="Line chart showing sales from Jan to Dec 2025"
 *   />
 */

'use client';

import React, { useRef, useEffect } from 'react';
import { TypeSafeChartRenderer } from '../charts/TypeSafeChartRenderer';
import { useKeyboardChartNavigation, useScreenReaderOnly } from '@/hooks/useKeyboardChartNavigation';
import { useAccessibleColors, ACCESSIBLE_CHART_COLORS } from '@/themes/accessible-colors';
import type { ChartConfig } from '@/types/charts.generated';

export interface AccessibleChartRendererProps {
  /**
   * Chart configuration (from backend Pydantic schemas)
   */
  config: ChartConfig;
  
  /**
   * Accessible title for the chart (required for ARIA)
   */
  title: string;
  
  /**
   * Detailed description for screen readers (optional but recommended)
   */
  description?: string;
  
  /**
   * Theme mode for colors (default: 'default')
   */
  theme?: 'default' | 'high-contrast';
  
  /**
   * Width of the chart
   */
  width?: number | string;
  
  /**
   * Height of the chart
   */
  height?: number;
  
  /**
   * Additional CSS class names
   */
  className?: string;
  
  /**
   * Enable keyboard navigation (default: true)
   */
  enableKeyboardNav?: boolean;
  
  /**
   * Callback when data point is focused
   */
  onDataPointFocus?: (index: number, point: any) => void;
}

/**
 * Accessible Chart Renderer Component.
 * 
 * Wraps TypeSafeChartRenderer with accessibility enhancements.
 */
export function AccessibleChartRenderer({
  config,
  title,
  description,
  theme = 'default',
  width = '100%',
  height = 300,
  className = '',
  enableKeyboardNav = true,
  onDataPointFocus,
}: AccessibleChartRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const accessibleColors = useAccessibleColors(theme);
  const srOnlyClass = useScreenReaderOnly();
  
  // Extract data from chart config for keyboard navigation
  const chartData = getChartData(config);
  
  // Setup keyboard navigation
  const {
    focusedIndex,
    focusedPoint,
    handleKeyDown,
    announcement,
    isNavigating,
  } = useKeyboardChartNavigation({
    data: chartData,
    announceKeys: getAnnounceKeys(config),
    onFocusChange: onDataPointFocus,
    enableAnnouncements: enableKeyboardNav,
  });
  
  // Apply accessible colors to config
  const accessibleConfig = applyAccessibleColors(config, accessibleColors.getColors());
  
  // Generate detailed summary for screen readers
  const chartSummary = generateChartSummary(config, title, description);
  
  // Auto-focus container when navigating
  useEffect(() => {
    if (isNavigating && containerRef.current) {
      containerRef.current.focus();
    }
  }, [isNavigating]);
  
  return (
    <div className={`accessible-chart-container ${className}`}>
      {/* Visible title */}
      <h3 className="text-lg font-semibold mb-2 text-gray-900">
        {title}
      </h3>
      
      {/* Chart wrapper with ARIA and keyboard support */}
      <div
        ref={containerRef}
        className="chart-wrapper relative focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-lg"
        role="img"
        aria-label={title}
        aria-describedby="chart-description chart-instructions"
        tabIndex={enableKeyboardNav ? 0 : -1}
        onKeyDown={enableKeyboardNav ? handleKeyDown : undefined}
      >
        {/* Screen reader description */}
        <div id="chart-description" className={srOnlyClass}>
          {chartSummary}
        </div>
        
        {/* Keyboard instructions */}
        {enableKeyboardNav && (
          <div id="chart-instructions" className={srOnlyClass}>
            Press arrow keys to navigate between data points. 
            Press Enter to hear details. 
            Press Escape to exit navigation.
          </div>
        )}
        
        {/* Live region for announcements */}
        {enableKeyboardNav && (
          <div
            className={srOnlyClass}
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            {announcement}
          </div>
        )}
        
        {/* Actual chart */}
        <TypeSafeChartRenderer
          config={accessibleConfig}
          width={width}
          height={height}
        />
        
        {/* Focus indicator overlay */}
        {isNavigating && focusedIndex >= 0 && (
          <div className="absolute top-2 right-2 bg-blue-600 text-white px-3 py-1 rounded-md text-sm shadow-lg">
            Point {focusedIndex + 1} of {chartData.length}
          </div>
        )}
      </div>
      
      {/* Optional visible description */}
      {description && (
        <p className="mt-2 text-sm text-gray-600">
          {description}
        </p>
      )}
      
      {/* Data table alternative (collapsible) */}
      <details className="mt-4 border border-gray-200 rounded-lg p-4">
        <summary className="cursor-pointer font-medium text-gray-700 hover:text-gray-900">
          View Data Table
        </summary>
        <div className="mt-4 overflow-x-auto">
          <ChartDataTable config={config} />
        </div>
      </details>
      
      {/* Accessibility metadata */}
      <div className="mt-2 text-xs text-gray-500">
        <span className="inline-flex items-center gap-1">
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v3.586L7.707 9.293a1 1 0 00-1.414 1.414l3 3a1 1 0 001.414 0l3-3a1 1 0 00-1.414-1.414L11 10.586V7z" clipRule="evenodd" />
          </svg>
          Colorblind-safe palette · Keyboard accessible · WCAG 2.1 AA compliant
        </span>
      </div>
    </div>
  );
}

/**
 * Extract data from chart config.
 */
function getChartData(config: ChartConfig): any[] {
  if ('data' in config && Array.isArray(config.data)) {
    return config.data;
  }
  return [];
}

/**
 * Get keys to announce for chart type.
 */
function getAnnounceKeys(config: ChartConfig): string[] {
  if ('x_key' in config && 'y_key' in config) {
    return [config.x_key, config.y_key];
  }
  if ('label_key' in config && 'value_key' in config) {
    return [config.label_key, config.value_key];
  }
  return [];
}

/**
 * Apply accessible colors to chart config.
 */
function applyAccessibleColors(config: ChartConfig, colors: string[]): ChartConfig {
  // Clone config to avoid mutation
  const newConfig = JSON.parse(JSON.stringify(config)) as ChartConfig;
  
  // Apply colors based on chart type
  if ('colors' in newConfig && Array.isArray(newConfig.colors)) {
    newConfig.colors = colors.slice(0, newConfig.colors.length);
  }
  
  return newConfig;
}

/**
 * Generate comprehensive chart summary for screen readers.
 */
function generateChartSummary(
  config: ChartConfig,
  title: string,
  description?: string
): string {
  const chartType = config.type;
  const data = getChartData(config);
  const dataPoints = data.length;
  
  let summary = `${title}. `;
  
  if (description) {
    summary += `${description}. `;
  }
  
  summary += `This is a ${chartType} chart with ${dataPoints} data points. `;
  
  // Add range information if available
  if (chartType === 'line' || chartType === 'bar' || chartType === 'area') {
    const yKey = 'y_key' in config ? config.y_key : 'value';
    const values = data.map(d => d[yKey]).filter(v => typeof v === 'number');
    
    if (values.length > 0) {
      const min = Math.min(...values);
      const max = Math.max(...values);
      summary += `Values range from ${min.toLocaleString()} to ${max.toLocaleString()}. `;
    }
  }
  
  summary += 'Use arrow keys to navigate through the data points.';
  
  return summary;
}

/**
 * Data table component for chart data (accessible alternative).
 */
function ChartDataTable({ config }: { config: ChartConfig }) {
  const data = getChartData(config);
  
  if (data.length === 0) {
    return <p className="text-gray-500">No data available</p>;
  }
  
  // Get column headers
  const columns = Object.keys(data[0]);
  
  return (
    <table className="min-w-full divide-y divide-gray-200">
      <thead className="bg-gray-50">
        <tr>
          {columns.map((col) => (
            <th
              key={col}
              scope="col"
              className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
            >
              {col}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="bg-white divide-y divide-gray-200">
        {data.map((row, index) => (
          <tr key={index} className="hover:bg-gray-50">
            {columns.map((col) => (
              <td
                key={col}
                className="px-4 py-2 text-sm text-gray-900 whitespace-nowrap"
              >
                {formatCellValue(row[col])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * Format cell value for table display.
 */
function formatCellValue(value: any): string {
  if (typeof value === 'number') {
    return value.toLocaleString();
  } else if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  } else if (value === null || value === undefined) {
    return '-';
  } else {
    return String(value);
  }
}

export default AccessibleChartRenderer;

