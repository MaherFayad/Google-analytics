/**
 * Queue Status Banner Component
 * 
 * Implements Task P0-31: Real-Time Queue Position Streaming via SSE
 * 
 * Displays real-time queue position and ETA for pending GA4 requests.
 * 
 * Features:
 * - Real-time SSE connection to backend
 * - Displays position in queue and ETA
 * - Visual progress indication
 * - Auto-dismisses when completed
 * 
 * Usage:
 *   <QueueStatusBanner requestId="abc-123" />
 */

import React, { useEffect, useState, useCallback } from 'react';
import { Clock, Users, AlertCircle, CheckCircle, X } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';

interface QueueStatus {
  request_id: string;
  position: number;
  total_queue: number;
  eta_seconds: number;
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'not_found';
  message: string;
  timestamp: string;
}

interface QueueStatusBannerProps {
  requestId: string;
  onComplete?: () => void;
  onError?: (error: string) => void;
  autoDismiss?: boolean;
  apiBaseUrl?: string;
}

export const QueueStatusBanner: React.FC<QueueStatusBannerProps> = ({
  requestId,
  onComplete,
  onError,
  autoDismiss = true,
  apiBaseUrl = '/api/v1',
}) => {
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDismissed, setIsDismissed] = useState(false);

  const connectSSE = useCallback(() => {
    const eventSource = new EventSource(
      `${apiBaseUrl}/analytics/queue/${requestId}`
    );

    eventSource.addEventListener('queue_status', (event) => {
      try {
        const status: QueueStatus = JSON.parse(event.data);
        setQueueStatus(status);
        setIsConnected(true);

        // Handle completion
        if (status.status === 'completed') {
          setIsConnected(false);
          onComplete?.();
          
          if (autoDismiss) {
            setTimeout(() => setIsDismissed(true), 3000);
          }
        }

        // Handle failure
        if (status.status === 'failed') {
          setError(status.message);
          setIsConnected(false);
          onError?.(status.message);
        }
      } catch (err) {
        console.error('Error parsing queue status:', err);
      }
    });

    eventSource.addEventListener('error', () => {
      setIsConnected(false);
      setError('Lost connection to server');
      eventSource.close();
    });

    return eventSource;
  }, [requestId, onComplete, onError, autoDismiss, apiBaseUrl]);

  useEffect(() => {
    const eventSource = connectSSE();

    return () => {
      eventSource.close();
    };
  }, [connectSSE]);

  // Format ETA for display
  const formatETA = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds} seconds`;
    } else if (seconds < 3600) {
      const minutes = Math.ceil(seconds / 60);
      return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
    } else {
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.ceil((seconds % 3600) / 60);
      return `${hours}h ${minutes}m`;
    }
  };

  // Calculate progress percentage
  const getProgressPercentage = (): number => {
    if (!queueStatus) return 0;
    if (queueStatus.status === 'completed') return 100;
    if (queueStatus.status === 'processing') return 90;
    if (queueStatus.total_queue === 0) return 0;
    
    const progressThroughQueue = 
      ((queueStatus.total_queue - queueStatus.position) / queueStatus.total_queue) * 100;
    
    return Math.max(5, Math.min(85, progressThroughQueue));
  };

  // Get variant for alert
  const getAlertVariant = () => {
    if (error || queueStatus?.status === 'failed') return 'destructive';
    if (queueStatus?.status === 'completed') return 'default';
    return 'default';
  };

  // Get icon for status
  const getStatusIcon = () => {
    if (queueStatus?.status === 'completed') {
      return <CheckCircle className="h-4 w-4 text-green-600" />;
    }
    if (queueStatus?.status === 'failed' || error) {
      return <AlertCircle className="h-4 w-4 text-red-600" />;
    }
    if (queueStatus?.status === 'processing') {
      return <Clock className="h-4 w-4 text-blue-600 animate-spin" />;
    }
    return <Users className="h-4 w-4 text-amber-600" />;
  };

  // Don't render if dismissed
  if (isDismissed) {
    return null;
  }

  // Don't render if no status yet
  if (!queueStatus && !error) {
    return null;
  }

  return (
    <Alert variant={getAlertVariant()} className="mb-4 relative">
      <div className="flex items-start gap-2">
        {getStatusIcon()}
        
        <div className="flex-1">
          <AlertDescription>
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium">
                {error ? 'Error' : queueStatus?.message}
              </span>
              
              {!autoDismiss && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-4 w-4 p-0"
                  onClick={() => setIsDismissed(true)}
                >
                  <X className="h-3 w-3" />
                </Button>
              )}
            </div>

            {queueStatus && queueStatus.status === 'queued' && (
              <div className="space-y-2 text-sm text-muted-foreground">
                <div className="flex items-center justify-between">
                  <span>
                    Position {queueStatus.position} of {queueStatus.total_queue}
                  </span>
                  <span>
                    ETA: {formatETA(queueStatus.eta_seconds)}
                  </span>
                </div>
                
                <Progress value={getProgressPercentage()} className="h-2" />
                
                <div className="flex items-center gap-2 text-xs">
                  <div className={`h-2 w-2 rounded-full ${
                    isConnected ? 'bg-green-500 animate-pulse' : 'bg-gray-400'
                  }`} />
                  <span>
                    {isConnected ? 'Connected' : 'Reconnecting...'}
                  </span>
                </div>
              </div>
            )}

            {queueStatus?.status === 'processing' && (
              <div className="text-sm text-muted-foreground">
                Your request is being processed...
              </div>
            )}

            {error && (
              <div className="text-sm text-red-600 mt-1">
                {error}
              </div>
            )}
          </AlertDescription>
        </div>
      </div>
    </Alert>
  );
};

// Example usage in a parent component
export const ExampleUsage: React.FC = () => {
  const [requestId, setRequestId] = useState<string | null>(null);

  const handleQuerySubmit = async () => {
    // Submit query to backend
    const response = await fetch('/api/v1/analytics/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: 'Show me last week traffic'
      })
    });
    
    const data = await response.json();
    setRequestId(data.query_id);
  };

  return (
    <div>
      <button onClick={handleQuerySubmit}>
        Submit Analytics Query
      </button>

      {requestId && (
        <QueueStatusBanner
          requestId={requestId}
          onComplete={() => {
            console.log('Request completed!');
            // Refresh results or show success message
          }}
          onError={(error) => {
            console.error('Request failed:', error);
            // Show error notification
          }}
        />
      )}
    </div>
  );
};

export default QueueStatusBanner;

