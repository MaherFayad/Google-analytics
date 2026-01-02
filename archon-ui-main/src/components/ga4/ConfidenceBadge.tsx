/**
 * Confidence Badge Component
 * 
 * Displays RAG confidence status with explanatory tooltips.
 * Implements Task P0-19: RAG Retrieval Confidence Filtering
 * 
 * Part of Task 10.2: GA4 Analytics Dashboard Component
 */

'use client';

import React, { useState } from 'react';

interface ConfidenceBadgeProps {
  confidence: number;
  status: 'high_confidence' | 'medium_confidence' | 'low_confidence' | 'no_relevant_context';
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({ confidence, status }) => {
  const [showTooltip, setShowTooltip] = useState(false);

  const getStatusConfig = () => {
    switch (status) {
      case 'high_confidence':
        return {
          label: 'High Confidence',
          color: 'bg-green-100 text-green-800 border-green-200',
          icon: '✓',
          description: 'This analysis is based on highly relevant historical data. Results are reliable.',
        };
      case 'medium_confidence':
        return {
          label: 'Medium Confidence',
          color: 'bg-blue-100 text-blue-800 border-blue-200',
          icon: '~',
          description: `This analysis is based on moderately relevant patterns (${(confidence * 100).toFixed(0)}% confidence). Consider as general guidance.`,
        };
      case 'low_confidence':
        return {
          label: 'Low Confidence',
          color: 'bg-yellow-100 text-yellow-800 border-yellow-200',
          icon: '⚠',
          description: `This analysis is based on loosely related patterns (${(confidence * 100).toFixed(0)}% confidence). Consider as exploratory analysis.`,
        };
      case 'no_relevant_context':
        return {
          label: 'No Historical Context',
          color: 'bg-gray-100 text-gray-800 border-gray-200',
          icon: 'ℹ',
          description: 'No relevant historical patterns found. Analysis is based solely on current data.',
        };
      default:
        return {
          label: 'Unknown',
          color: 'bg-gray-100 text-gray-800 border-gray-200',
          icon: '?',
          description: 'Confidence status unknown',
        };
    }
  };

  const config = getStatusConfig();

  return (
    <div className="relative inline-block">
      <div
        className={`flex items-center space-x-2 px-4 py-2 rounded-lg border ${config.color} cursor-help`}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <span className="text-lg">{config.icon}</span>
        <div className="flex flex-col">
          <span className="text-xs font-semibold uppercase tracking-wide">{config.label}</span>
          {status !== 'no_relevant_context' && (
            <span className="text-xs">{(confidence * 100).toFixed(1)}% confidence</span>
          )}
        </div>
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </div>

      {/* Tooltip */}
      {showTooltip && (
        <div className="absolute z-10 w-64 p-3 mt-2 text-sm bg-gray-900 text-white rounded-lg shadow-lg">
          <p className="leading-relaxed">{config.description}</p>
          <div className="absolute -top-1 left-6 w-2 h-2 bg-gray-900 transform rotate-45"></div>
        </div>
      )}
    </div>
  );
};

export default ConfidenceBadge;

