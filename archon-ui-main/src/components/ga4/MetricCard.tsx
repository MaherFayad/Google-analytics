/**
 * Metric Card Component
 * 
 * Displays a single key metric with optional change percentage and trend indicator.
 * 
 * Part of Task 10.2: GA4 Analytics Dashboard Component
 */

'use client';

import React from 'react';

interface MetricCardProps {
  metric: {
    label: string;
    value: string;
    change?: string;
    trend?: 'up' | 'down' | 'neutral';
  };
}

export const MetricCard: React.FC<MetricCardProps> = ({ metric }) => {
  const getTrendColor = () => {
    if (!metric.trend) return 'text-gray-600';
    
    switch (metric.trend) {
      case 'up':
        return 'text-green-600';
      case 'down':
        return 'text-red-600';
      case 'neutral':
      default:
        return 'text-gray-600';
    }
  };

  const getTrendIcon = () => {
    if (!metric.trend) return null;
    
    switch (metric.trend) {
      case 'up':
        return (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
          </svg>
        );
      case 'down':
        return (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
          </svg>
        );
      case 'neutral':
        return (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14" />
          </svg>
        );
      default:
        return null;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow">
      <div className="flex flex-col">
        <span className="text-sm font-medium text-gray-600 mb-2">{metric.label}</span>
        
        <div className="flex items-baseline justify-between">
          <span className="text-2xl font-bold text-gray-900">{metric.value}</span>
          
          {metric.change && (
            <div className={`flex items-center space-x-1 ${getTrendColor()}`}>
              {getTrendIcon()}
              <span className="text-sm font-semibold">{metric.change}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MetricCard;

