/**
 * Analytics Page with Error Boundaries
 * 
 * Implements Task 6.2: Global Error Boundary Integration Example
 * 
 * Shows how to properly integrate error boundaries in production.
 */

'use client';

import React from 'react';
import { ChatLayout } from '@/components/ga4/ChatLayout';
import { ChatErrorBoundary } from '@/components/errors';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Create QueryClient for TanStack Query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60000, // 1 minute
      retry: 1,
    },
  },
});

/**
 * Analytics Page with Error Protection
 * 
 * Structure:
 * - QueryClientProvider (for useChatSessions hook)
 * - ChatErrorBoundary (catches all chat/rendering errors)
 * - ChatLayout (history sidebar + chat interface)
 */
export default function AnalyticsPage() {
  /**
   * Error handler for logging errors to external service
   */
  const handleError = (error: Error, errorInfo: React.ErrorInfo) => {
    // Log to console in development
    console.error('Analytics page error:', error, errorInfo);

    // In production, send to error tracking service
    // Example: Sentry.captureException(error, { extra: errorInfo });
  };

  return (
    <QueryClientProvider client={queryClient}>
      <ChatErrorBoundary
        onError={handleError}
        showDetails={process.env.NODE_ENV === 'development'}
      >
        <div className="h-screen flex flex-col">
          {/* Page Header */}
          <header className="bg-white border-b px-6 py-4">
            <h1 className="text-2xl font-bold text-gray-900">
              Google Analytics Chat
            </h1>
            <p className="text-sm text-gray-600 mt-1">
              Ask questions about your analytics data in natural language
            </p>
          </header>

          {/* Chat Interface */}
          <main className="flex-1 overflow-hidden">
            <ChatLayout />
          </main>
        </div>
      </ChatErrorBoundary>
    </QueryClientProvider>
  );
}

