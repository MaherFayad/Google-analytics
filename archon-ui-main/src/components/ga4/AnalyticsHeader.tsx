/**
 * Analytics Header Component
 * 
 * Header for the analytics dashboard with navigation and actions.
 * 
 * Part of Task 10.2: GA4 Analytics Dashboard Component
 */

'use client';

import React from 'react';

export const AnalyticsHeader: React.FC = () => {
  return (
    <header className="bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              GA4 Analytics Dashboard
            </h1>
            <p className="mt-1 text-sm text-gray-600">
              Ask natural language questions about your Google Analytics data
            </p>
          </div>
          
          <div className="flex items-center space-x-4">
            {/* Property Selector (placeholder) */}
            <select className="block px-3 py-2 text-sm border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500">
              <option>All Properties</option>
              {/* TODO: Populate from tenant context */}
            </select>
            
            {/* Settings Link */}
            <a
              href="/settings"
              className="text-gray-600 hover:text-gray-900 transition-colors"
              title="Settings"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                />
              </svg>
            </a>
          </div>
        </div>
      </div>
    </header>
  );
};

export default AnalyticsHeader;

