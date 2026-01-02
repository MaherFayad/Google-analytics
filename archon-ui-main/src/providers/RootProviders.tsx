/**
 * Root Providers Component
 * 
 * Implements Task 10.1: Application-wide Provider Setup
 * 
 * Wraps the application with all necessary providers:
 * - NextAuth SessionProvider
 * - TenantProvider for multi-tenant context
 * - React Query for data fetching
 * 
 * Usage in app/layout.tsx:
 *   import { RootProviders } from '@/providers/RootProviders';
 *   
 *   export default function RootLayout({ children }) {
 *     return (
 *       <html>
 *         <body>
 *           <RootProviders>{children}</RootProviders>
 *         </body>
 *       </html>
 *     );
 *   }
 */

'use client';

import React from 'react';
import { SessionProvider } from 'next-auth/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TenantProvider } from '@/contexts/TenantContext';

interface RootProvidersProps {
  children: React.ReactNode;
  session?: any;
}

// Create Query Client with default options
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  },
});

/**
 * Root providers wrapper
 * 
 * Order matters:
 * 1. SessionProvider - Provides authentication context
 * 2. QueryClientProvider - Provides React Query functionality
 * 3. TenantProvider - Provides tenant context (depends on session)
 */
export const RootProviders: React.FC<RootProvidersProps> = ({ 
  children, 
  session 
}) => {
  return (
    <SessionProvider session={session}>
      <QueryClientProvider client={queryClient}>
        <TenantProvider>
          {children}
        </TenantProvider>
      </QueryClientProvider>
    </SessionProvider>
  );
};

export default RootProviders;

