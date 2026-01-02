/**
 * Query Input Component
 * 
 * Natural language query input with submit handling.
 * 
 * Part of Task 10.2: GA4 Analytics Dashboard Component
 */

'use client';

import React, { useState, FormEvent } from 'react';

interface QueryInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (query: string) => void;
  isLoading?: boolean;
  placeholder?: string;
}

export const QueryInput: React.FC<QueryInputProps> = ({
  value,
  onChange,
  onSubmit,
  isLoading = false,
  placeholder = 'Ask about your analytics...',
}) => {
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim() && !isLoading) {
      onSubmit(value.trim());
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as any);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <svg
            className="h-5 w-5 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </div>
        
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyPress={handleKeyPress}
          disabled={isLoading}
          placeholder={placeholder}
          className="block w-full pl-10 pr-32 py-4 text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
        />
        
        <div className="absolute inset-y-0 right-0 flex items-center pr-3">
          <button
            type="submit"
            disabled={isLoading || !value.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? (
              <span className="flex items-center">
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Analyzing...
              </span>
            ) : (
              'Analyze'
            )}
          </button>
        </div>
      </div>
      
      {/* Example Queries */}
      <div className="mt-2 flex flex-wrap gap-2">
        <span className="text-xs text-gray-500">Examples:</span>
        {[
          'Show mobile conversions last week',
          'Compare desktop vs mobile traffic',
          'Bounce rate trends this month',
        ].map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => {
              onChange(example);
              onSubmit(example);
            }}
            disabled={isLoading}
            className="text-xs px-2 py-1 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {example}
          </button>
        ))}
      </div>
    </form>
  );
};

export default QueryInput;

