/**
 * SSE Auto-Reconnect Hook with Exponential Backoff
 * 
 * Implements Task P0-34: SSE Auto-Reconnect with Idempotency & Backoff
 * 
 * Features:
 * - Automatic reconnection with exponential backoff (2s, 4s, 8s, 16s)
 * - Idempotency tokens prevent duplicate requests
 * - Manual retry capability
 * - Connection status tracking
 * - Max 5 retry attempts
 * 
 * Usage:
 *   const { status, retryCount, reconnect } = useSSEAutoReconnect(
 *     '/api/v1/analytics/stream',
 *     'request-123'
 *   );
 */

'use client';

import { useEffect, useState, useRef, useCallback } from 'react';

export type ConnectionStatus = 'connected' | 'connecting' | 'reconnecting' | 'failed' | 'disconnected';

export interface SSEMessage {
  type: string;
  data: any;
  timestamp: string;
}

export interface UseSSEAutoReconnectOptions {
  maxRetries?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
  onMessage?: (message: SSEMessage) => void;
  onError?: (error: Event) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

export interface UseSSEAutoReconnectReturn {
  status: ConnectionStatus;
  retryCount: number;
  backoffSeconds: number;
  reconnect: () => void;
  disconnect: () => void;
  lastMessage: SSEMessage | null;
  error: string | null;
}

/**
 * Hook for SSE connections with automatic reconnection
 * 
 * Implements exponential backoff:
 * - Attempt 0: 2 seconds
 * - Attempt 1: 4 seconds
 * - Attempt 2: 8 seconds
 * - Attempt 3: 16 seconds
 * - Attempt 4: 16 seconds (capped)
 * - Attempt 5+: Give up
 * 
 * @param url - SSE endpoint URL
 * @param requestId - Idempotency token for request deduplication
 * @param options - Configuration options
 * @returns Connection state and control functions
 */
export function useSSEAutoReconnect(
  url: string,
  requestId: string,
  options: UseSSEAutoReconnectOptions = {}
): UseSSEAutoReconnectReturn {
  const {
    maxRetries = 5,
    initialBackoffMs = 2000,
    maxBackoffMs = 16000,
    onMessage,
    onError,
    onConnect,
    onDisconnect,
  } = options;

  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const [retryCount, setRetryCount] = useState(0);
  const [backoffSeconds, setBackoffSeconds] = useState(0);
  const [lastMessage, setLastMessage] = useState<SSEMessage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const retryTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const backoffIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const isManualDisconnectRef = useRef(false);

  /**
   * Calculate exponential backoff delay
   */
  const calculateBackoff = useCallback((attempt: number): number => {
    const backoff = Math.min(
      initialBackoffMs * Math.pow(2, attempt),
      maxBackoffMs
    );
    return backoff;
  }, [initialBackoffMs, maxBackoffMs]);

  /**
   * Clean up existing connection
   */
  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }

    if (backoffIntervalRef.current) {
      clearInterval(backoffIntervalRef.current);
      backoffIntervalRef.current = null;
    }

    setBackoffSeconds(0);
  }, []);

  /**
   * Connect to SSE endpoint
   */
  const connect = useCallback((attempt: number) => {
    // Check if max retries exceeded
    if (attempt >= maxRetries) {
      setStatus('failed');
      setError(`Connection failed after ${maxRetries} attempts`);
      cleanup();
      return;
    }

    // Clean up previous connection
    cleanup();

    // Calculate backoff for this attempt
    const backoffMs = calculateBackoff(attempt);
    const backoffSec = Math.ceil(backoffMs / 1000);

    // Update status
    if (attempt === 0) {
      setStatus('connecting');
    } else {
      setStatus('reconnecting');
      setBackoffSeconds(backoffSec);

      // Countdown timer for UX
      let remainingSeconds = backoffSec;
      backoffIntervalRef.current = setInterval(() => {
        remainingSeconds--;
        setBackoffSeconds(remainingSeconds);
        if (remainingSeconds <= 0 && backoffIntervalRef.current) {
          clearInterval(backoffIntervalRef.current);
        }
      }, 1000);
    }

    setRetryCount(attempt);

    // Schedule reconnection with backoff
    retryTimeoutRef.current = setTimeout(() => {
      try {
        // Build URL with idempotency token
        const urlWithParams = new URL(url, window.location.origin);
        urlWithParams.searchParams.set('request_id', requestId);
        urlWithParams.searchParams.set('retry_attempt', attempt.toString());

        // Create EventSource
        const eventSource = new EventSource(urlWithParams.toString());

        // Connection opened
        eventSource.onopen = () => {
          setStatus('connected');
          setRetryCount(0);
          setError(null);
          cleanup();
          onConnect?.();
        };

        // Message received
        eventSource.onmessage = (event) => {
          try {
            const message: SSEMessage = {
              type: 'message',
              data: JSON.parse(event.data),
              timestamp: new Date().toISOString(),
            };
            setLastMessage(message);
            onMessage?.(message);
          } catch (err) {
            console.error('Error parsing SSE message:', err);
          }
        };

        // Custom event types
        eventSource.addEventListener('status', (event: any) => {
          try {
            const message: SSEMessage = {
              type: 'status',
              data: JSON.parse(event.data),
              timestamp: new Date().toISOString(),
            };
            setLastMessage(message);
            onMessage?.(message);
          } catch (err) {
            console.error('Error parsing status event:', err);
          }
        });

        eventSource.addEventListener('result', (event: any) => {
          try {
            const message: SSEMessage = {
              type: 'result',
              data: JSON.parse(event.data),
              timestamp: new Date().toISOString(),
            };
            setLastMessage(message);
            onMessage?.(message);
            
            // Connection complete
            eventSource.close();
            setStatus('disconnected');
            onDisconnect?.();
          } catch (err) {
            console.error('Error parsing result event:', err);
          }
        });

        // Error handling
        eventSource.onerror = (event) => {
          console.error('SSE connection error:', event);
          
          setError('Connection error');
          onError?.(event);

          // Close and retry (unless manually disconnected)
          eventSource.close();
          
          if (!isManualDisconnectRef.current) {
            // Retry with incremented attempt count
            connect(attempt + 1);
          }
        };

        eventSourceRef.current = eventSource;
      } catch (err) {
        console.error('Error creating EventSource:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
        
        // Retry
        if (!isManualDisconnectRef.current) {
          connect(attempt + 1);
        }
      }
    }, backoffMs);
  }, [
    url,
    requestId,
    maxRetries,
    calculateBackoff,
    cleanup,
    onMessage,
    onError,
    onConnect,
    onDisconnect,
  ]);

  /**
   * Manually trigger reconnection
   */
  const reconnect = useCallback(() => {
    isManualDisconnectRef.current = false;
    setError(null);
    connect(0);
  }, [connect]);

  /**
   * Manually disconnect
   */
  const disconnect = useCallback(() => {
    isManualDisconnectRef.current = true;
    cleanup();
    setStatus('disconnected');
    onDisconnect?.();
  }, [cleanup, onDisconnect]);

  // Initial connection
  useEffect(() => {
    isManualDisconnectRef.current = false;
    connect(0);

    // Cleanup on unmount
    return () => {
      isManualDisconnectRef.current = true;
      cleanup();
    };
  }, [connect, cleanup]);

  return {
    status,
    retryCount,
    backoffSeconds,
    reconnect,
    disconnect,
    lastMessage,
    error,
  };
}

export default useSSEAutoReconnect;

