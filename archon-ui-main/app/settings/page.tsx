/**
 * Settings Page
 * 
 * Implements Task 10.3: OAuth Connection Status UI
 * 
 * Features:
 * - GA4 connection management
 * - OAuth status display
 * - Property list with sync status
 * - Connection/disconnection controls
 */

'use client';

import React from 'react';
import { useSession } from 'next-auth/react';
import { GA4ConnectionCard } from '@/components/ga4/GA4ConnectionCard';

export default function SettingsPage() {
  const { data: session, status } = useSession();

  if (status === 'loading') {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading settings...</p>
        </div>
      </div>
    );
  }

  if (status === 'unauthenticated') {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center max-w-md">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">
            Authentication Required
          </h2>
          <p className="text-gray-600 mb-6">
            Please sign in to access your settings.
          </p>
          <a
            href="/auth/signin"
            className="inline-flex items-center justify-center px-4 py-2 border border-transparent text-base font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
          >
            Sign In
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
          <p className="mt-2 text-gray-600">
            Manage your account settings and GA4 connections
          </p>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="space-y-8">
          {/* Account Info */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              Account Information
            </h2>
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="space-y-3">
                <div>
                  <span className="text-sm font-medium text-gray-600">Email:</span>
                  <p className="text-gray-900">{session?.user?.email || 'N/A'}</p>
                </div>
                <div>
                  <span className="text-sm font-medium text-gray-600">Name:</span>
                  <p className="text-gray-900">{session?.user?.name || 'N/A'}</p>
                </div>
              </div>
            </div>
          </section>

          {/* GA4 Connections */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              Data Connections
            </h2>
            <GA4ConnectionCard userId={(session?.user as any)?.id || 'unknown'} />
          </section>

          {/* Additional Settings Sections */}
          <section>
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              Preferences
            </h2>
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <p className="text-gray-600 text-sm">
                Additional preferences coming soon...
              </p>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

