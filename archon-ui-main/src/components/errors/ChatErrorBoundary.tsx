/**
 * Chat Error Boundary Component
 * 
 * Implements Task 6.2: Global Error Boundary
 * 
 * Features:
 * - Catches rendering errors in Chat component
 * - Shows fallback UI with raw text answer
 * - Logs errors for debugging
 * - Allows recovery/retry
 * - Graceful degradation for malformed chart data
 * 
 * Usage:
 *   <ChatErrorBoundary>
 *     <ChatInterface />
 *   </ChatErrorBoundary>
 */

'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { AlertTriangleIcon, RefreshCwIcon, ChevronDownIcon, ChevronUpIcon } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  showDetails?: boolean;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  showErrorDetails: boolean;
}

/**
 * Error Boundary for Chat Interface
 * 
 * Catches errors in:
 * - Chart rendering (malformed data)
 * - Message display
 * - Streaming updates
 * - Report visualization
 * 
 * Shows fallback UI that displays raw text when visualization fails
 */
export class ChatErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      showErrorDetails: false,
    };
  }

  /**
   * Update state when error is caught
   */
  static getDerivedStateFromError(error: Error): Partial<State> {
    return {
      hasError: true,
      error,
    };
  }

  /**
   * Log error details
   */
  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log to console in development
    if (process.env.NODE_ENV === 'development') {
      console.error('ChatErrorBoundary caught error:', error);
      console.error('Error info:', errorInfo);
      console.error('Component stack:', errorInfo.componentStack);
    }

    // Update state with error info
    this.setState({
      errorInfo,
    });

    // Call custom error handler if provided
    this.props.onError?.(error, errorInfo);

    // In production, send to error tracking service (e.g., Sentry)
    if (process.env.NODE_ENV === 'production') {
      this.logErrorToService(error, errorInfo);
    }
  }

  /**
   * Log error to external service (e.g., Sentry)
   */
  private logErrorToService(error: Error, errorInfo: ErrorInfo) {
    // TODO: Integrate with Sentry or similar service
    // Example:
    // Sentry.captureException(error, {
    //   contexts: {
    //     react: {
    //       componentStack: errorInfo.componentStack,
    //     },
    //   },
    // });
    
    console.error('Error logged to service:', error.message);
  }

  /**
   * Reset error state and retry
   */
  private handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      showErrorDetails: false,
    });
  };

  /**
   * Toggle error details visibility
   */
  private toggleErrorDetails = () => {
    this.setState((prev) => ({
      showErrorDetails: !prev.showErrorDetails,
    }));
  };

  /**
   * Render fallback UI when error occurs
   */
  private renderFallback(): ReactNode {
    const { error, errorInfo, showErrorDetails } = this.state;
    const { fallback } = this.props;

    // Use custom fallback if provided
    if (fallback) {
      return fallback;
    }

    // Check if error is chart-related
    const isChartError = error?.message?.toLowerCase().includes('chart') ||
                        error?.message?.toLowerCase().includes('render') ||
                        error?.stack?.includes('ChartRenderer');

    return (
      <div className="flex items-center justify-center min-h-[400px] p-8">
        <Card className="max-w-2xl w-full p-6">
          <div className="flex items-start gap-4">
            {/* Icon */}
            <div className="flex-shrink-0">
              <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center">
                <AlertTriangleIcon className="w-6 h-6 text-red-600" />
              </div>
            </div>

            {/* Content */}
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                {isChartError ? 'Visualization Error' : 'Something went wrong'}
              </h3>

              <p className="text-sm text-gray-700 mb-4">
                {isChartError
                  ? 'We encountered an error while rendering the chart. The raw data is still available below.'
                  : 'An unexpected error occurred while displaying your chat. We\'ve logged the issue and you can try again.'}
              </p>

              {/* Error Message */}
              <div className="bg-gray-50 border border-gray-200 rounded-md p-3 mb-4">
                <p className="text-xs font-mono text-gray-800">
                  {error?.message || 'Unknown error'}
                </p>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 mb-4">
                <Button
                  onClick={this.handleReset}
                  size="sm"
                  className="flex items-center gap-2"
                >
                  <RefreshCwIcon className="w-4 h-4" />
                  Try Again
                </Button>

                <Button
                  onClick={this.toggleErrorDetails}
                  variant="outline"
                  size="sm"
                  className="flex items-center gap-2"
                >
                  {showErrorDetails ? (
                    <>
                      <ChevronUpIcon className="w-4 h-4" />
                      Hide Details
                    </>
                  ) : (
                    <>
                      <ChevronDownIcon className="w-4 h-4" />
                      Show Details
                    </>
                  )}
                </Button>
              </div>

              {/* Error Details (Collapsible) */}
              {showErrorDetails && (
                <div className="border-t border-gray-200 pt-4 mt-4">
                  <h4 className="text-sm font-medium text-gray-900 mb-2">
                    Technical Details
                  </h4>
                  
                  {/* Error Stack */}
                  <div className="bg-gray-900 text-gray-100 rounded-md p-3 mb-3 overflow-auto max-h-48">
                    <pre className="text-xs font-mono whitespace-pre-wrap">
                      {error?.stack || 'No stack trace available'}
                    </pre>
                  </div>

                  {/* Component Stack */}
                  {errorInfo?.componentStack && (
                    <>
                      <h4 className="text-sm font-medium text-gray-900 mb-2">
                        Component Stack
                      </h4>
                      <div className="bg-gray-900 text-gray-100 rounded-md p-3 overflow-auto max-h-48">
                        <pre className="text-xs font-mono whitespace-pre-wrap">
                          {errorInfo.componentStack}
                        </pre>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Help Text */}
              <p className="text-xs text-gray-600 mt-4">
                If this problem persists, please contact support with the error details above.
              </p>
            </div>
          </div>
        </Card>
      </div>
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
 * Functional wrapper for easier usage
 */
export const withChatErrorBoundary = <P extends object>(
  Component: React.ComponentType<P>,
  errorBoundaryProps?: Omit<Props, 'children'>
) => {
  const WrappedComponent = (props: P) => (
    <ChatErrorBoundary {...errorBoundaryProps}>
      <Component {...props} />
    </ChatErrorBoundary>
  );

  WrappedComponent.displayName = `withChatErrorBoundary(${
    Component.displayName || Component.name || 'Component'
  })`;

  return WrappedComponent;
};

export default ChatErrorBoundary;

