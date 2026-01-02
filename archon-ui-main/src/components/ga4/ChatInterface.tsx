/**
 * Chat Interface Component
 * 
 * Implements Task 5.3: The Chat Interface & Stream Hook
 * 
 * Features:
 * - Message display with user/assistant roles
 * - Input field with send button
 * - Streaming status indicator
 * - Report rendering with charts and metrics
 * - Auto-scroll to bottom
 * - Retry failed messages
 * 
 * Usage:
 *   <ChatInterface endpoint="/api/v1/chat/stream" />
 */

'use client';

import React, { useRef, useEffect, useState } from 'react';
import { useChatStream } from '@/hooks/useChatStream';
import { ChartRenderer } from '@/components/charts/ChartRenderer';
import { MetricCard } from './MetricCard';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  SendIcon,
  RefreshCwIcon,
  AlertCircleIcon,
  LoaderIcon,
} from 'lucide-react';

export interface ChatInterfaceProps {
  endpoint?: string;
  placeholder?: string;
  className?: string;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  endpoint = '/api/v1/chat/stream',
  placeholder = 'Ask about your analytics... (e.g., "Show me sessions last week")',
  className = '',
}) => {
  const {
    messages,
    isStreaming,
    sendMessage,
    clearMessages,
    retryLastMessage,
    connectionStatus,
    error,
  } = useChatStream({ endpoint });

  const [inputValue, setInputValue] = useState('');
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  /**
   * Auto-scroll to bottom when new messages arrive
   */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /**
   * Handle send message
   */
  const handleSend = async () => {
    if (!inputValue.trim() || isStreaming) {
      return;
    }

    await sendMessage(inputValue);
    setInputValue('');
  };

  /**
   * Handle Enter key press
   */
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={`chat-interface flex flex-col h-full ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <h2 className="text-xl font-semibold">Analytics Chat</h2>
        <div className="flex items-center gap-2">
          <ConnectionStatusBadge status={connectionStatus} />
          {messages.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={clearMessages}
              disabled={isStreaming}
            >
              Clear Chat
            </Button>
          )}
        </div>
      </div>

      {/* Messages Area */}
      <ScrollArea ref={scrollAreaRef} className="flex-1 p-4">
        <div className="space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-gray-500 py-12">
              <p className="text-lg mb-2">Welcome to Analytics Chat</p>
              <p className="text-sm">Ask questions about your Google Analytics data</p>
              <div className="mt-6 space-y-2 text-left max-w-md mx-auto">
                <p className="text-sm font-medium">Example queries:</p>
                <ul className="text-sm space-y-1 list-disc list-inside text-gray-600">
                  <li>"Show me sessions for the last 7 days"</li>
                  <li>"What's my bounce rate by device?"</li>
                  <li>"Compare traffic sources this month"</li>
                  <li>"Show me conversion trends"</li>
                </ul>
              </div>
            </div>
          )}

          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}

          {/* Error Display */}
          {error && (
            <Card className="p-4 bg-red-50 border-red-200">
              <div className="flex items-start gap-3">
                <AlertCircleIcon className="w-5 h-5 text-red-600 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-red-900">Error</p>
                  <p className="text-sm text-red-700 mt-1">{error}</p>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={retryLastMessage}
                    className="mt-2"
                  >
                    <RefreshCwIcon className="w-4 h-4 mr-1" />
                    Retry
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {/* Scroll anchor */}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input Area */}
      <div className="p-4 border-t bg-white">
        <div className="flex items-center gap-2">
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={placeholder}
            disabled={isStreaming}
            className="flex-1"
          />
          <Button
            onClick={handleSend}
            disabled={!inputValue.trim() || isStreaming}
            size="icon"
          >
            {isStreaming ? (
              <LoaderIcon className="w-4 h-4 animate-spin" />
            ) : (
              <SendIcon className="w-4 h-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};

/**
 * Message Bubble Component
 */
const MessageBubble: React.FC<{ message: any }> = ({ message }) => {
  const isUser = message.role === 'user';
  const isStreaming = message.status === 'streaming';
  const isError = message.status === 'error';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-3xl ${isUser ? 'w-auto' : 'w-full'}`}>
        <Card
          className={`p-4 ${
            isUser
              ? 'bg-blue-600 text-white'
              : isError
              ? 'bg-red-50 border-red-200'
              : 'bg-white'
          }`}
        >
          {/* User message */}
          {isUser && (
            <p className="text-sm">{message.content}</p>
          )}

          {/* Assistant message - Streaming */}
          {!isUser && isStreaming && (
            <div className="flex items-center gap-2">
              <LoaderIcon className="w-4 h-4 animate-spin text-blue-600" />
              <span className="text-sm text-gray-600">
                {message.streamingStatus || 'Thinking...'}
              </span>
            </div>
          )}

          {/* Assistant message - Complete */}
          {!isUser && !isStreaming && message.report && (
            <div className="space-y-4">
              {/* Answer text */}
              {message.report.answer && (
                <div className="prose prose-sm max-w-none">
                  <p className="whitespace-pre-wrap">{message.report.answer}</p>
                </div>
              )}

              {/* Metric Cards */}
              {message.report.metrics && message.report.metrics.length > 0 && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {message.report.metrics.map((metric: any, idx: number) => (
                    <MetricCard key={idx} {...metric} />
                  ))}
                </div>
              )}

              {/* Charts */}
              {message.report.charts && message.report.charts.length > 0 && (
                <div className="space-y-6">
                  {message.report.charts.map((chart: any, idx: number) => (
                    <ChartRenderer
                      key={idx}
                      config={chart}
                      className="bg-gray-50 p-4 rounded-lg"
                    />
                  ))}
                </div>
              )}

              {/* Confidence Badge */}
              {message.report.confidence !== undefined && (
                <div className="text-xs text-gray-500">
                  Confidence: {(message.report.confidence * 100).toFixed(0)}%
                </div>
              )}
            </div>
          )}

          {/* Error message */}
          {!isUser && isError && (
            <div className="flex items-start gap-2">
              <AlertCircleIcon className="w-4 h-4 text-red-600 mt-0.5" />
              <p className="text-sm text-red-700">{message.content}</p>
            </div>
          )}
        </Card>

        {/* Timestamp */}
        <p className="text-xs text-gray-500 mt-1 px-2">
          {message.timestamp.toLocaleTimeString()}
        </p>
      </div>
    </div>
  );
};

/**
 * Connection Status Badge
 */
const ConnectionStatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const statusConfig = {
    idle: { label: 'Ready', color: 'bg-gray-200 text-gray-700' },
    connecting: { label: 'Connecting...', color: 'bg-yellow-200 text-yellow-700' },
    connected: { label: 'Connected', color: 'bg-green-200 text-green-700' },
    error: { label: 'Error', color: 'bg-red-200 text-red-700' },
  };

  const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.idle;

  return (
    <div className={`px-2 py-1 rounded-full text-xs font-medium ${config.color}`}>
      {config.label}
    </div>
  );
};

export default ChatInterface;

