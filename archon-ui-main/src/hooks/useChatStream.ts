/**
 * Chat Stream Hook
 * 
 * Implements Task 5.3: The Chat Interface & Stream Hook
 * 
 * Features:
 * - Messages array state management
 * - Streaming status tracking
 * - "Thinking" placeholder with live updates
 * - Automatic result rendering
 * - SSE connection management
 * 
 * Usage:
 *   const { messages, isStreaming, sendMessage } = useChatStream('/api/v1/chat/stream');
 *   
 *   <button onClick={() => sendMessage('Show me sessions')}>Send</button>
 *   {messages.map(msg => <Message key={msg.id} {...msg} />)}
 */

'use client';

import { useState, useCallback, useRef, useEffect } from 'react';

/**
 * Simple UUID generator (no external dependency)
 */
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export type MessageRole = 'user' | 'assistant' | 'system';
export type MessageStatus = 'pending' | 'streaming' | 'complete' | 'error';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  status: MessageStatus;
  
  // For assistant messages with structured data
  report?: {
    answer: string;
    charts: any[];
    metrics: any[];
    confidence: number;
  };
  
  // For streaming status updates
  streamingStatus?: string;
}

export interface UseChatStreamOptions {
  endpoint: string;
  onError?: (error: Error) => void;
  onMessageComplete?: (message: ChatMessage) => void;
  autoConnect?: boolean;
}

export interface UseChatStreamReturn {
  messages: ChatMessage[];
  isStreaming: boolean;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
  retryLastMessage: () => Promise<void>;
  connectionStatus: 'idle' | 'connecting' | 'connected' | 'error';
  error: string | null;
}

/**
 * Hook for chat interface with SSE streaming
 * 
 * Implements Task 5.3 requirements:
 * - State: messages (Array), isStreaming (Boolean)
 * - On submit: append user message, add "Thinking" placeholder
 * - SSE updates: update placeholder with status events
 * - On result: replace placeholder with rendered Report component
 */
export function useChatStream(
  options: UseChatStreamOptions
): UseChatStreamReturn {
  const { endpoint, onError, onMessageComplete } = options;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'idle' | 'connecting' | 'connected' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const lastUserMessageRef = useRef<string>('');
  const currentAssistantMessageIdRef = useRef<string | null>(null);

  /**
   * Close existing SSE connection
   */
  const closeConnection = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setConnectionStatus('idle');
  }, []);

  /**
   * Send a chat message and start streaming response
   */
  const sendMessage = useCallback(async (content: string) => {
    try {
      setIsStreaming(true);
      setError(null);
      lastUserMessageRef.current = content;

      // 1. Append user message
      const userMessage: ChatMessage = {
        id: generateId(),
        role: 'user',
        content,
        timestamp: new Date(),
        status: 'complete',
      };

      setMessages(prev => [...prev, userMessage]);

      // 2. Add "Thinking" placeholder for assistant
      const assistantMessageId = generateId();
      currentAssistantMessageIdRef.current = assistantMessageId;

      const thinkingMessage: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        status: 'streaming',
        streamingStatus: 'Thinking...',
      };

      setMessages(prev => [...prev, thinkingMessage]);

      // 3. Open SSE connection
      setConnectionStatus('connecting');

      const urlWithParams = new URL(endpoint, window.location.origin);
      urlWithParams.searchParams.set('query', content);
      urlWithParams.searchParams.set('request_id', assistantMessageId);

      const eventSource = new EventSource(urlWithParams.toString());

      eventSource.onopen = () => {
        setConnectionStatus('connected');
      };

      // 4. Handle status events (update "Thinking" message)
      eventSource.addEventListener('status', (event: any) => {
        try {
          const data = JSON.parse(event.data);
          const statusText = data.message || data.status || 'Processing...';

          setMessages(prev =>
            prev.map(msg =>
              msg.id === assistantMessageId
                ? { ...msg, streamingStatus: statusText }
                : msg
            )
          );
        } catch (err) {
          console.error('Error parsing status event:', err);
        }
      });

      // 5. Handle result event (replace placeholder with full report)
      eventSource.addEventListener('result', (event: any) => {
        try {
          const result = JSON.parse(event.data);

          // Replace placeholder with complete message
          setMessages(prev =>
            prev.map(msg =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    content: result.answer || 'Report generated',
                    report: result,
                    status: 'complete',
                    streamingStatus: undefined,
                  }
                : msg
            )
          );

          // Cleanup
          eventSource.close();
          setIsStreaming(false);
          setConnectionStatus('idle');
          currentAssistantMessageIdRef.current = null;

          // Callback
          if (onMessageComplete) {
            const completedMessage = messages.find(m => m.id === assistantMessageId);
            if (completedMessage) {
              onMessageComplete(completedMessage);
            }
          }
        } catch (err) {
          console.error('Error parsing result event:', err);
          handleError(new Error('Failed to parse result'));
        }
      });

      // 6. Handle errors
      eventSource.onerror = (event) => {
        console.error('SSE connection error:', event);
        handleError(new Error('Connection error'));
        eventSource.close();
      };

      eventSourceRef.current = eventSource;

    } catch (err) {
      const error = err instanceof Error ? err : new Error('Unknown error');
      handleError(error);
    }
  }, [endpoint, onMessageComplete, messages]);

  /**
   * Handle errors
   */
  const handleError = useCallback((err: Error) => {
    setError(err.message);
    setIsStreaming(false);
    setConnectionStatus('error');
    closeConnection();

    // Mark assistant message as error
    if (currentAssistantMessageIdRef.current) {
      setMessages(prev =>
        prev.map(msg =>
          msg.id === currentAssistantMessageIdRef.current
            ? {
                ...msg,
                content: `Error: ${err.message}`,
                status: 'error',
                streamingStatus: undefined,
              }
            : msg
        )
      );
      currentAssistantMessageIdRef.current = null;
    }

    onError?.(err);
  }, [closeConnection, onError]);

  /**
   * Retry the last user message
   */
  const retryLastMessage = useCallback(async () => {
    if (lastUserMessageRef.current) {
      await sendMessage(lastUserMessageRef.current);
    }
  }, [sendMessage]);

  /**
   * Clear all messages
   */
  const clearMessages = useCallback(() => {
    setMessages([]);
    closeConnection();
    setIsStreaming(false);
    setError(null);
  }, [closeConnection]);

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      closeConnection();
    };
  }, [closeConnection]);

  return {
    messages,
    isStreaming,
    sendMessage,
    clearMessages,
    retryLastMessage,
    connectionStatus,
    error,
  };
}

export default useChatStream;

