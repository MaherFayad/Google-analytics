/**
 * Chart Error Boundary Component
 * 
 * Implements Task 6.2: Global Error Boundary (Chart-specific)
 * 
 * Features:
 * - Catches errors in chart rendering
 * - Falls back to raw text/data table
 * - Shows chart data in JSON format
 * - Allows data download
 * 
 * Usage:
 *   <ChartErrorBoundary chartData={data}>
 *     <ChartRenderer config={chartConfig} />
 *   </ChartErrorBoundary>
 */

'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { AlertCircleIcon, DownloadIcon, TableIcon } from 'lucide-react';

interface Props {
  children: ReactNode;
  chartData?: any;
  chartTitle?: string;
  onError?: (error: Error) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  showRawData: boolean;
}

/**
 * Error Boundary specifically for chart components
 * 
 * When chart rendering fails (e.g., malformed data):
 * - Shows fallback UI with raw text answer
 * - Displays data in table format
 * - Allows JSON download
 */
export class ChartErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      showRawData: false,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ChartErrorBoundary caught error:', error);
    console.error('Error info:', errorInfo);

    this.props.onError?.(error);
  }

  /**
   * Download chart data as JSON
   */
  private handleDownloadData = () => {
    const { chartData, chartTitle } = this.props;

    if (!chartData) return;

    const jsonStr = JSON.stringify(chartData, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${chartTitle || 'chart-data'}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  /**
   * Toggle raw data display
   */
  private toggleRawData = () => {
    this.setState((prev) => ({ showRawData: !prev.showRawData }));
  };

  /**
   * Render data as table
   */
  private renderDataTable(): ReactNode {
    const { chartData } = this.props;

    if (!chartData) {
      return <p className="text-sm text-gray-600">No data available</p>;
    }

    // Handle array of objects
    if (Array.isArray(chartData.data)) {
      const data = chartData.data;
      if (data.length === 0) {
        return <p className="text-sm text-gray-600">No data points</p>;
      }

      const keys = Object.keys(data[0]);

      return (
        <div className="overflow-auto max-h-64">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {keys.map((key) => (
                  <th
                    key={key}
                    className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase tracking-wider"
                  >
                    {key}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {data.map((row: any, idx: number) => (
                <tr key={idx}>
                  {keys.map((key) => (
                    <td key={key} className="px-3 py-2 whitespace-nowrap text-gray-900">
                      {typeof row[key] === 'number'
                        ? row[key].toLocaleString()
                        : row[key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }

    // Fallback to JSON display
    return (
      <pre className="text-xs bg-gray-50 p-3 rounded-md overflow-auto max-h-64">
        {JSON.stringify(chartData, null, 2)}
      </pre>
    );
  }

  /**
   * Render fallback UI
   */
  private renderFallback(): ReactNode {
    const { error, showRawData } = this.state;
    const { chartTitle, chartData } = this.props;

    return (
      <Card className="p-4 bg-yellow-50 border-yellow-200">
        <div className="flex items-start gap-3 mb-3">
          <AlertCircleIcon className="w-5 h-5 text-yellow-600 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <h4 className="text-sm font-medium text-yellow-900 mb-1">
              Chart Rendering Failed
            </h4>
            <p className="text-xs text-yellow-800 mb-2">
              {chartTitle || 'This chart'} could not be displayed due to a rendering error.
            </p>
            <p className="text-xs text-yellow-700">
              Error: {error?.message || 'Unknown error'}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 mb-3">
          {chartData && (
            <>
              <Button
                onClick={this.toggleRawData}
                variant="outline"
                size="sm"
                className="flex items-center gap-1 text-xs"
              >
                <TableIcon className="w-3 h-3" />
                {showRawData ? 'Hide Data' : 'Show Data'}
              </Button>
              <Button
                onClick={this.handleDownloadData}
                variant="outline"
                size="sm"
                className="flex items-center gap-1 text-xs"
              >
                <DownloadIcon className="w-3 h-3" />
                Download JSON
              </Button>
            </>
          )}
        </div>

        {/* Raw Data Table */}
        {showRawData && chartData && (
          <div className="border-t border-yellow-200 pt-3">
            <h5 className="text-xs font-medium text-yellow-900 mb-2">
              Raw Data
            </h5>
            {this.renderDataTable()}
          </div>
        )}
      </Card>
    );
  }

  render() {
    if (this.state.hasError) {
      return this.renderFallback();
    }

    return this.props.children;
  }
}

/**
 * HOC wrapper for easier usage
 */
export const withChartErrorBoundary = <P extends object>(
  Component: React.ComponentType<P>
) => {
  const WrappedComponent = (props: P & { chartData?: any; chartTitle?: string }) => {
    const { chartData, chartTitle, ...componentProps } = props;
    
    return (
      <ChartErrorBoundary chartData={chartData} chartTitle={chartTitle}>
        <Component {...(componentProps as P)} />
      </ChartErrorBoundary>
    );
  };

  WrappedComponent.displayName = `withChartErrorBoundary(${
    Component.displayName || Component.name || 'Component'
  })`;

  return WrappedComponent;
};

export default ChartErrorBoundary;

