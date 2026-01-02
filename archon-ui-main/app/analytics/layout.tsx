/**
 * Analytics Layout
 * 
 * Layout wrapper for the analytics dashboard with providers.
 * 
 * Part of Task 10.2: GA4 Analytics Dashboard Component
 */

import React from 'react';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import { RootProviders } from '@/providers/RootProviders';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000, // 1 minute
      refetchOnWindowFocus: false,
    },
  },
});

export default function AnalyticsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RootProviders>
      {children}
    </RootProviders>
  );
}

export const metadata = {
  title: 'GA4 Analytics Dashboard',
  description: 'AI-powered Google Analytics 4 insights and reporting',
};

