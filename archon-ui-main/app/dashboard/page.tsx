/**
 * Main Dashboard Page
 * 
 * Unified interface for GA4 Analytics Chat with History
 * 
 * Features:
 * - Integrated chat interface with streaming responses
 * - Chat history sidebar with session management
 * - Real-time SSE connection status
 * - Protected route (requires authentication)
 * - Tenant context integration
 * 
 * Route: /dashboard
 */

'use client';

import React from 'react';
import { useSession } from 'next-auth/react';
import { redirect } from 'next/navigation';
import { ChatLayout } from '@/components/ga4/ChatLayout';
import { ConnectionStatusIndicator } from '@/components/ga4/ConnectionStatus';
import { GA4ConnectionCard } from '@/components/ga4/GA4ConnectionCard';
import { TenantSelector } from '@/components/tenant/TenantSelector';
import { Button } from '@/components/ui/button';
import { LogOutIcon, SettingsIcon } from 'lucide-react';
import Link from 'next/link';

export default function DashboardPage() {
  const { data: session, status } = useSession();

  // Redirect to login if not authenticated
  if (status === 'unauthenticated') {
    redirect('/auth/signin');
  }

  // Loading state
  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-100">
      {/* Top Navigation Bar */}
      <header className="bg-white border-b shadow-sm">
        <div className="px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold text-gray-900">
              GA4 Analytics Chat
            </h1>
            
            {/* Tenant Selector */}
            <TenantSelector />
          </div>

          <div className="flex items-center gap-3">
            {/* Connection Status */}
            <ConnectionStatusIndicator status="connected" />

            {/* User Menu */}
            <div className="flex items-center gap-2 border-l pl-3">
              <div className="text-right mr-2">
                <p className="text-sm font-medium text-gray-900">
                  {session?.user?.name || 'User'}
                </p>
                <p className="text-xs text-gray-500">
                  {session?.user?.email || ''}
                </p>
              </div>

              <Link href="/settings">
                <Button variant="ghost" size="icon" title="Settings">
                  <SettingsIcon className="w-5 h-5" />
                </Button>
              </Link>

              <Button
                variant="ghost"
                size="icon"
                onClick={() => {
                  if (typeof window !== 'undefined') {
                    window.location.href = '/api/auth/signout';
                  }
                }}
                title="Sign Out"
              >
                <LogOutIcon className="w-5 h-5" />
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* GA4 Connection Banner */}
      {session?.user?.id && (
        <div className="bg-blue-50 border-b">
          <div className="px-4 py-2">
            <GA4ConnectionCard userId={session.user.id} />
          </div>
        </div>
      )}

      {/* Main Chat Layout */}
      <main className="flex-1 overflow-hidden">
        <ChatLayout 
          showSidebar={true}
          sidebarWidth="320px"
        />
      </main>

      {/* Footer */}
      <footer className="bg-white border-t py-2 px-4">
        <div className="flex items-center justify-between text-xs text-gray-500">
          <p>
            GA4 Analytics Chat &middot; Powered by AI
          </p>
          <div className="flex items-center gap-4">
            <Link href="/docs" className="hover:text-gray-700">
              Documentation
            </Link>
            <Link href="/support" className="hover:text-gray-700">
              Support
            </Link>
            <a
              href="https://github.com/yourusername/ga4-analytics"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-gray-700"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

