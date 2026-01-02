/**
 * Tenant Context for Multi-Tenant Management
 * 
 * Implements Task 10.1: Tenant Context Provider
 * 
 * Features:
 * - Stores current tenant ID in localStorage and React Context
 * - Provides tenant switching capabilities
 * - Integrates with NextAuth session
 * - Ensures tenant context is available throughout the app
 * 
 * Usage:
 *   import { useTenant } from '@/contexts/TenantContext';
 *   
 *   function MyComponent() {
 *     const { tenantId, setTenantId, tenants } = useTenant();
 *     // ...
 *   }
 */

'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useSession } from 'next-auth/react';

export interface Tenant {
  id: string;
  name: string;
  role: 'owner' | 'admin' | 'member' | 'viewer';
  created_at: string;
  updated_at: string;
}

interface TenantContextValue {
  tenantId: string | null;
  setTenantId: (tenantId: string) => void;
  tenants: Tenant[];
  setTenants: (tenants: Tenant[]) => void;
  currentTenant: Tenant | null;
  isLoading: boolean;
  error: string | null;
  refreshTenants: () => Promise<void>;
}

const TenantContext = createContext<TenantContextValue | undefined>(undefined);

const TENANT_ID_KEY = 'archon_tenant_id';

interface TenantProviderProps {
  children: React.ReactNode;
  apiBaseUrl?: string;
}

export const TenantProvider: React.FC<TenantProviderProps> = ({ 
  children,
  apiBaseUrl = '/api/v1'
}) => {
  const { data: session, status } = useSession();
  const [tenantId, setTenantIdState] = useState<string | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load tenant ID from localStorage on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const storedTenantId = localStorage.getItem(TENANT_ID_KEY);
      if (storedTenantId) {
        setTenantIdState(storedTenantId);
      }
    }
  }, []);

  // Set tenant ID and persist to localStorage
  const setTenantId = useCallback((newTenantId: string) => {
    setTenantIdState(newTenantId);
    if (typeof window !== 'undefined') {
      localStorage.setItem(TENANT_ID_KEY, newTenantId);
    }
  }, []);

  // Fetch user's tenants from API
  const refreshTenants = useCallback(async () => {
    if (status !== 'authenticated' || !session?.accessToken) {
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      const response = await fetch(`${apiBaseUrl}/tenants`, {
        headers: {
          'Authorization': `Bearer ${session.accessToken}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch tenants: ${response.statusText}`);
      }

      const data = await response.json();
      const fetchedTenants: Tenant[] = data.tenants || [];
      
      setTenants(fetchedTenants);

      // Auto-select first tenant if none selected
      if (!tenantId && fetchedTenants.length > 0) {
        setTenantId(fetchedTenants[0].id);
      }

      // Validate current tenant selection
      if (tenantId && !fetchedTenants.some(t => t.id === tenantId)) {
        // Current tenant not in list, select first available
        if (fetchedTenants.length > 0) {
          setTenantId(fetchedTenants[0].id);
        } else {
          setTenantId('');
        }
      }
    } catch (err) {
      console.error('Error fetching tenants:', err);
      setError(err instanceof Error ? err.message : 'Failed to load tenants');
    } finally {
      setIsLoading(false);
    }
  }, [status, session, tenantId, setTenantId, apiBaseUrl]);

  // Fetch tenants when session becomes available
  useEffect(() => {
    if (status === 'authenticated') {
      refreshTenants();
    } else if (status === 'unauthenticated') {
      setIsLoading(false);
      setTenants([]);
      setTenantIdState(null);
      if (typeof window !== 'undefined') {
        localStorage.removeItem(TENANT_ID_KEY);
      }
    }
  }, [status, refreshTenants]);

  // Find current tenant object
  const currentTenant = tenants.find(t => t.id === tenantId) || null;

  const value: TenantContextValue = {
    tenantId,
    setTenantId,
    tenants,
    setTenants,
    currentTenant,
    isLoading,
    error,
    refreshTenants,
  };

  return (
    <TenantContext.Provider value={value}>
      {children}
    </TenantContext.Provider>
  );
};

/**
 * Hook to access tenant context
 * 
 * @throws Error if used outside TenantProvider
 * 
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { tenantId, setTenantId, currentTenant } = useTenant();
 *   
 *   return (
 *     <div>
 *       <p>Current Tenant: {currentTenant?.name}</p>
 *       <button onClick={() => setTenantId('other-tenant-id')}>
 *         Switch Tenant
 *       </button>
 *     </div>
 *   );
 * }
 * ```
 */
export const useTenant = (): TenantContextValue => {
  const context = useContext(TenantContext);
  
  if (context === undefined) {
    throw new Error('useTenant must be used within a TenantProvider');
  }
  
  return context;
};

/**
 * Hook to require tenant selection
 * 
 * Throws error if no tenant is selected, ensuring components
 * that require a tenant context will fail gracefully.
 * 
 * @example
 * ```tsx
 * function TenantSpecificComponent() {
 *   const { tenantId, currentTenant } = useRequireTenant();
 *   // tenantId is guaranteed to be non-null here
 *   
 *   return <div>Tenant: {currentTenant.name}</div>;
 * }
 * ```
 */
export const useRequireTenant = (): TenantContextValue & { 
  tenantId: string; 
  currentTenant: Tenant 
} => {
  const context = useTenant();
  
  if (!context.tenantId || !context.currentTenant) {
    throw new Error('This component requires a tenant to be selected');
  }
  
  return {
    ...context,
    tenantId: context.tenantId,
    currentTenant: context.currentTenant,
  };
};

export default TenantContext;

