/**
 * React Hook for API Client with Session Integration
 * 
 * Implements Task 10.1: NextAuth Integration with API Client
 * 
 * Automatically configures API client with NextAuth session token
 * and tenant context.
 * 
 * Usage:
 *   import { useApiClient } from '@/hooks/useApiClient';
 *   
 *   function MyComponent() {
 *     const api = useApiClient();
 *     
 *     const fetchData = async () => {
 *       const response = await api.get('/analytics/data');
 *     };
 *   }
 */

'use client';

import { useEffect, useMemo } from 'react';
import { useSession } from 'next-auth/react';
import { AxiosInstance } from 'axios';
import { apiClient, configureApiClientAuth } from '@/lib/api-client';
import { useTenant } from '@/contexts/TenantContext';

/**
 * Hook that returns configured API client with session token
 */
export const useApiClient = (): AxiosInstance => {
  const { data: session } = useSession();
  const { tenantId } = useTenant();

  // Configure auth when session changes
  useEffect(() => {
    if (session?.accessToken) {
      configureApiClientAuth(session.accessToken as string);
    }
  }, [session]);

  // Return memoized client
  return useMemo(() => apiClient, []);
};

/**
 * Hook that requires both session and tenant context
 * 
 * Throws error if either is missing
 */
export const useAuthenticatedApiClient = (): AxiosInstance => {
  const { data: session, status } = useSession();
  const { tenantId } = useTenant();

  if (status === 'loading') {
    throw new Error('Session is loading');
  }

  if (status === 'unauthenticated' || !session) {
    throw new Error('User is not authenticated. Please log in.');
  }

  if (!tenantId) {
    throw new Error('No tenant selected. Please select a workspace.');
  }

  // Configure auth
  useEffect(() => {
    if (session?.accessToken) {
      configureApiClientAuth(session.accessToken as string);
    }
  }, [session]);

  return useMemo(() => apiClient, []);
};

export default useApiClient;

