/**
 * Tenant Selector Component
 * 
 * Implements Task 10.1: Tenant Selection UI
 * 
 * Provides a dropdown for users to select which tenant context
 * they want to work in. Integrated with TenantContext.
 * 
 * Features:
 * - Lists all tenants user has access to
 * - Shows current tenant with role badge
 * - Persists selection to localStorage
 * - Visual feedback for tenant switching
 * 
 * Usage:
 *   <TenantSelector />
 */

'use client';

import React from 'react';
import { useTenant } from '@/contexts/TenantContext';
import { ChevronDown, Building2, Check, AlertCircle } from 'lucide-react';

interface TenantSelectorProps {
  className?: string;
  showRole?: boolean;
}

export const TenantSelector: React.FC<TenantSelectorProps> = ({ 
  className = '',
  showRole = true 
}) => {
  const { 
    tenantId, 
    setTenantId, 
    tenants, 
    currentTenant, 
    isLoading, 
    error 
  } = useTenant();

  const [isOpen, setIsOpen] = React.useState(false);

  // Role badge color mapping
  const getRoleBadgeColor = (role: string) => {
    switch (role) {
      case 'owner':
        return 'bg-purple-100 text-purple-800 border-purple-200';
      case 'admin':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'member':
        return 'bg-green-100 text-green-800 border-green-200';
      case 'viewer':
        return 'bg-gray-100 text-gray-800 border-gray-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  // Handle tenant selection
  const handleTenantSelect = (newTenantId: string) => {
    setTenantId(newTenantId);
    setIsOpen(false);
  };

  // Loading state
  if (isLoading) {
    return (
      <div className={`flex items-center gap-2 px-3 py-2 ${className}`}>
        <Building2 className="h-4 w-4 text-gray-400" />
        <span className="text-sm text-gray-500">Loading tenants...</span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className={`flex items-center gap-2 px-3 py-2 text-red-600 ${className}`}>
        <AlertCircle className="h-4 w-4" />
        <span className="text-sm">{error}</span>
      </div>
    );
  }

  // No tenants state
  if (tenants.length === 0) {
    return (
      <div className={`flex items-center gap-2 px-3 py-2 ${className}`}>
        <Building2 className="h-4 w-4 text-gray-400" />
        <span className="text-sm text-gray-500">No tenants available</span>
      </div>
    );
  }

  return (
    <div className={`relative ${className}`}>
      {/* Current tenant display */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between w-full px-3 py-2 text-sm bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Building2 className="h-4 w-4 text-gray-600 flex-shrink-0" />
          <div className="flex flex-col items-start min-w-0 flex-1">
            <span className="font-medium text-gray-900 truncate w-full">
              {currentTenant?.name || 'Select Tenant'}
            </span>
            {showRole && currentTenant && (
              <span className={`text-xs px-2 py-0.5 rounded-full border ${getRoleBadgeColor(currentTenant.role)} mt-0.5`}>
                {currentTenant.role}
              </span>
            )}
          </div>
        </div>
        <ChevronDown 
          className={`h-4 w-4 text-gray-400 transition-transform flex-shrink-0 ${
            isOpen ? 'transform rotate-180' : ''
          }`} 
        />
      </button>

      {/* Dropdown menu */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div 
            className="fixed inset-0 z-10" 
            onClick={() => setIsOpen(false)}
            aria-hidden="true"
          />
          
          {/* Menu */}
          <div 
            className="absolute z-20 w-full mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-auto"
            role="listbox"
          >
            {tenants.map((tenant) => (
              <button
                key={tenant.id}
                onClick={() => handleTenantSelect(tenant.id)}
                className={`w-full px-3 py-2 text-left hover:bg-gray-50 focus:bg-gray-50 focus:outline-none transition-colors ${
                  tenant.id === tenantId ? 'bg-blue-50' : ''
                }`}
                role="option"
                aria-selected={tenant.id === tenantId}
              >
                <div className="flex items-center justify-between">
                  <div className="flex flex-col gap-1 flex-1 min-w-0">
                    <span className={`text-sm font-medium truncate ${
                      tenant.id === tenantId ? 'text-blue-900' : 'text-gray-900'
                    }`}>
                      {tenant.name}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border w-fit ${getRoleBadgeColor(tenant.role)}`}>
                      {tenant.role}
                    </span>
                  </div>
                  {tenant.id === tenantId && (
                    <Check className="h-4 w-4 text-blue-600 flex-shrink-0 ml-2" />
                  )}
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

/**
 * Compact tenant selector for header/navbar
 */
export const CompactTenantSelector: React.FC = () => {
  return (
    <TenantSelector 
      className="min-w-[200px] max-w-[300px]" 
      showRole={false}
    />
  );
};

/**
 * Tenant selector with role badge for settings page
 */
export const DetailedTenantSelector: React.FC = () => {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-gray-700">
        Current Workspace
      </label>
      <TenantSelector 
        className="w-full" 
        showRole={true}
      />
      <p className="text-xs text-gray-500">
        All data and reports will be scoped to the selected workspace
      </p>
    </div>
  );
};

export default TenantSelector;

