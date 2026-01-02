/**
 * Connection Status Component
 * 
 * Implements Task P0-34: SSE Auto-Reconnect with Idempotency & Backoff
 * 
 * Displays real-time connection status for SSE streams with:
 * - Visual status indicators
 * - Retry countdown
 * - Manual reconnect button
 * - Error messages
 * 
 * Usage:
 *   <ConnectionStatus 
 *     status="reconnecting"
 *     retryCount={2}
 *     backoffSeconds={4}
 *     onReconnect={() => reconnect()}
 *   />
 */

'use client';

import React from 'react';
import {  Wifi, WifiOff, AlertCircle, CheckCircle, RefreshCw, X } from 'lucide-react';

export type ConnectionStatusType = 'connected' | 'connecting' | 'reconnecting' | 'failed' | 'disconnected';

export interface ConnectionStatusProps {
  status: ConnectionStatusType;
  retryCount?: number;
  backoffSeconds?: number;
  error?: string | null;
  onReconnect?: () => void;
  onDismiss?: () => void;
  className?: string;
  showWhenConnected?: boolean;
}

/**
 * Connection status banner component
 * 
 * Shows different UI states based on connection status
 */
export const ConnectionStatus: React.FC<ConnectionStatusProps> = ({
  status,
  retryCount = 0,
  backoffSeconds = 0,
  error = null,
  onReconnect,
  onDismiss,
  className = '',
  showWhenConnected = false,
}) => {
  // Don't show anything when connected (unless explicitly requested)
  if (status === 'connected' && !showWhenConnected) {
    return null;
  }

  // Get status-specific styling and content
  const getStatusConfig = () => {
    switch (status) {
      case 'connected':
        return {
          icon: <CheckCircle className="h-4 w-4 text-green-600" />,
          bgColor: 'bg-green-50 border-green-200',
          textColor: 'text-green-800',
          title: 'Connected',
          message: 'Stream connection active',
        };
      
      case 'connecting':
        return {
          icon: <Wifi className="h-4 w-4 text-blue-600 animate-pulse" />,
          bgColor: 'bg-blue-50 border-blue-200',
          textColor: 'text-blue-800',
          title: 'Connecting',
          message: 'Establishing connection...',
        };
      
      case 'reconnecting':
        return {
          icon: <RefreshCw className="h-4 w-4 text-amber-600 animate-spin" />,
          bgColor: 'bg-amber-50 border-amber-200',
          textColor: 'text-amber-800',
          title: 'Reconnecting',
          message: backoffSeconds > 0
            ? `Retrying in ${backoffSeconds}s... (Attempt ${retryCount + 1}/5)`
            : `Reconnecting... (Attempt ${retryCount + 1}/5)`,
        };
      
      case 'failed':
        return {
          icon: <AlertCircle className="h-4 w-4 text-red-600" />,
          bgColor: 'bg-red-50 border-red-200',
          textColor: 'text-red-800',
          title: 'Connection Failed',
          message: error || 'Connection failed after multiple attempts',
        };
      
      case 'disconnected':
        return {
          icon: <WifiOff className="h-4 w-4 text-gray-600" />,
          bgColor: 'bg-gray-50 border-gray-200',
          textColor: 'text-gray-800',
          title: 'Disconnected',
          message: 'Stream connection closed',
        };
      
      default:
        return {
          icon: <Wifi className="h-4 w-4" />,
          bgColor: 'bg-gray-50 border-gray-200',
          textColor: 'text-gray-800',
          title: 'Unknown',
          message: 'Connection status unknown',
        };
    }
  };

  const config = getStatusConfig();

  return (
    <div 
      className={`flex items-center justify-between px-4 py-3 border rounded-md ${config.bgColor} ${className}`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-3 flex-1">
        {config.icon}
        
        <div className="flex flex-col gap-1">
          <span className={`text-sm font-medium ${config.textColor}`}>
            {config.title}
          </span>
          <span className={`text-xs ${config.textColor} opacity-75`}>
            {config.message}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {/* Retry button for failed or disconnected states */}
        {(status === 'failed' || status === 'disconnected') && onReconnect && (
          <button
            onClick={onReconnect}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
              status === 'failed'
                ? 'bg-red-600 text-white hover:bg-red-700'
                : 'bg-gray-600 text-white hover:bg-gray-700'
            }`}
            aria-label="Reconnect"
          >
            <RefreshCw className="h-3 w-3 inline mr-1" />
            Retry Now
          </button>
        )}

        {/* Dismiss button */}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className={`p-1 rounded hover:bg-black/10 transition-colors ${config.textColor}`}
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
};

/**
 * Compact connection status indicator (for headers/navbars)
 */
export const ConnectionStatusIndicator: React.FC<{
  status: ConnectionStatusType;
  onClick?: () => void;
}> = ({ status, onClick }) => {
  const getIndicatorConfig = () => {
    switch (status) {
      case 'connected':
        return {
          icon: <CheckCircle className="h-4 w-4" />,
          color: 'text-green-600',
          title: 'Connected',
        };
      case 'connecting':
      case 'reconnecting':
        return {
          icon: <RefreshCw className="h-4 w-4 animate-spin" />,
          color: 'text-amber-600',
          title: 'Reconnecting...',
        };
      case 'failed':
        return {
          icon: <AlertCircle className="h-4 w-4" />,
          color: 'text-red-600',
          title: 'Connection Failed',
        };
      case 'disconnected':
        return {
          icon: <WifiOff className="h-4 w-4" />,
          color: 'text-gray-600',
          title: 'Disconnected',
        };
      default:
        return {
          icon: <Wifi className="h-4 w-4" />,
          color: 'text-gray-600',
          title: 'Unknown',
        };
    }
  };

  const config = getIndicatorConfig();

  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-2 py-1 rounded-md hover:bg-gray-100 transition-colors ${config.color}`}
      title={config.title}
      aria-label={config.title}
    >
      {config.icon}
      <span className="text-xs font-medium hidden sm:inline">
        {status === 'connected' ? 'Live' : status}
      </span>
    </button>
  );
};

/**
 * Example usage in a dashboard
 */
export const ExampleUsage: React.FC = () => {
  const [dismissed, setDismissed] = React.useState(false);

  // Example: Using with useSSEAutoReconnect hook
  // const { status, retryCount, backoffSeconds, reconnect } = useSSEAutoReconnect(
  //   '/api/v1/analytics/stream',
  //   'request-123'
  // );

  // Mock status for demonstration
  const [status] = React.useState<ConnectionStatusType>('reconnecting');
  const [retryCount] = React.useState(2);
  const [backoffSeconds] = React.useState(4);

  if (dismissed) {
    return null;
  }

  return (
    <div className="space-y-4">
      {/* Full status banner */}
      <ConnectionStatus
        status={status}
        retryCount={retryCount}
        backoffSeconds={backoffSeconds}
        onReconnect={() => console.log('Reconnecting...')}
        onDismiss={() => setDismissed(true)}
      />

      {/* Compact indicator for header */}
      <div className="flex items-center justify-between p-4 bg-white border rounded-md">
        <span className="text-sm font-medium">Analytics Dashboard</span>
        <ConnectionStatusIndicator
          status={status}
          onClick={() => console.log('Show connection details')}
        />
      </div>
    </div>
  );
};

export default ConnectionStatus;

