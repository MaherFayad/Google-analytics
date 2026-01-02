/**
 * GA4 Connection Card Component
 * 
 * Implements Task 10.3: OAuth Connection Status UI
 * 
 * Features:
 * - Display GA4 connection status
 * - List all connected properties
 * - Show last sync time
 * - Token expiry status
 * - "Connect New Property" button
 * - Disconnect option
 */

'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { signIn } from 'next-auth/react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface GA4Property {
  property_id: string;
  property_name: string | null;
  last_sync: string | null;
  is_active: boolean;
  token_expires_at: string;
}

interface GA4StatusResponse {
  authenticated: boolean;
  properties: GA4Property[];
  total_properties: number;
}

interface GA4ConnectionCardProps {
  userId: string;
}

export function GA4ConnectionCard({ userId }: GA4ConnectionCardProps) {
  const queryClient = useQueryClient();
  const [isConnecting, setIsConnecting] = useState(false);

  // Fetch GA4 connection status
  const { data, isLoading, error } = useQuery<GA4StatusResponse>({
    queryKey: ['ga4-status', userId],
    queryFn: async () => {
      const response = await axios.get(`/api/v1/auth/ga4/status`, {
        params: { user_id: userId }
      });
      return response.data;
    },
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Connect to Google Analytics
  const handleConnect = async () => {
    setIsConnecting(true);
    try {
      // Trigger NextAuth OAuth flow
      await signIn('google', {
        callbackUrl: '/settings',
        redirect: true,
      });
    } catch (err) {
      console.error('Failed to connect:', err);
      setIsConnecting(false);
    }
  };

  // Format relative time
  const formatRelativeTime = (isoDate: string | null): string => {
    if (!isoDate) return 'Never';
    
    const date = new Date(isoDate);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString();
  };

  // Loading state
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Google Analytics 4 Connections</CardTitle>
          <CardDescription>Loading connection status...</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Error state
  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Google Analytics 4 Connections</CardTitle>
          <CardDescription>Failed to load connection status</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-600 text-sm">
              {(error as Error).message || 'An error occurred'}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const hasConnections = data && data.authenticated && data.properties.length > 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Google Analytics 4 Connections</CardTitle>
            <CardDescription>
              Manage your GA4 property connections and OAuth status
            </CardDescription>
          </div>
          <Button 
            onClick={handleConnect} 
            disabled={isConnecting}
            variant={hasConnections ? "outline" : "default"}
          >
            {isConnecting ? 'Connecting...' : hasConnections ? 'Connect Another Property' : 'Connect Google Analytics'}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {!hasConnections ? (
          // Empty state
          <div className="text-center py-8 bg-gray-50 rounded-lg border border-gray-200">
            <div className="mx-auto w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4">
              <svg
                className="w-8 h-8 text-blue-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              No Connections Yet
            </h3>
            <p className="text-gray-600 text-sm max-w-sm mx-auto mb-4">
              Connect your Google Analytics 4 property to start analyzing your data with AI-powered insights.
            </p>
          </div>
        ) : (
          // Connected properties list
          <div className="space-y-4">
            {data.properties.map((property) => (
              <div
                key={property.property_id}
                className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <h4 className="font-semibold text-gray-900">
                        {property.property_name || 'Unnamed Property'}
                      </h4>
                      <Badge variant={property.is_active ? "default" : "destructive"}>
                        {property.is_active ? 'Active' : 'Expired'}
                      </Badge>
                    </div>
                    
                    <div className="space-y-1 text-sm text-gray-600">
                      <p>
                        <span className="font-medium">Property ID:</span>{' '}
                        <code className="px-1.5 py-0.5 bg-gray-100 rounded text-xs">
                          {property.property_id}
                        </code>
                      </p>
                      <p>
                        <span className="font-medium">Last Sync:</span>{' '}
                        {formatRelativeTime(property.last_sync)}
                      </p>
                      <p>
                        <span className="font-medium">Token Expires:</span>{' '}
                        {formatRelativeTime(property.token_expires_at)}
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-col gap-2">
                    {!property.is_active && (
                      <Button 
                        size="sm" 
                        variant="outline"
                        onClick={handleConnect}
                      >
                        Reconnect
                      </Button>
                    )}
                    <Button 
                      size="sm" 
                      variant="ghost"
                      className="text-red-600 hover:text-red-700 hover:bg-red-50"
                    >
                      Disconnect
                    </Button>
                  </div>
                </div>
              </div>
            ))}

            <div className="pt-4 border-t border-gray-200">
              <p className="text-sm text-gray-600">
                <span className="font-medium">{data.total_properties}</span> {data.total_properties === 1 ? 'property' : 'properties'} connected
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

