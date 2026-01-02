/**
 * Pattern Card Component
 * 
 * Displays historical pattern matches from RAG retrieval.
 * Shows similarity score and relevant metrics.
 * 
 * Part of Task 10.2: GA4 Analytics Dashboard Component
 */

'use client';

import React from 'react';

interface PatternCardProps {
  pattern: {
    description: string;
    similarity_score: number;
    date_range: string;
    metric_values: Record<string, any>;
  };
}

export const PatternCard: React.FC<PatternCardProps> = ({ pattern }) => {
  const confidencePercentage = (pattern.similarity_score * 100).toFixed(1);
  
  const getConfidenceColor = () => {
    if (pattern.similarity_score >= 0.85) return 'bg-green-100 text-green-800 border-green-200';
    if (pattern.similarity_score >= 0.70) return 'bg-blue-100 text-blue-800 border-blue-200';
    if (pattern.similarity_score >= 0.50) return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    return 'bg-gray-100 text-gray-800 border-gray-200';
  };

  const formatMetricValue = (key: string, value: any): string => {
    if (typeof value === 'number') {
      if (key.toLowerCase().includes('rate') || key.toLowerCase().includes('percent')) {
        return `${(value * 100).toFixed(1)}%`;
      }
      if (value > 1000) {
        return value.toLocaleString();
      }
      return value.toFixed(2);
    }
    return String(value);
  };

  return (
    <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow border border-gray-200">
      {/* Header with Confidence Badge */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-900 mb-1">Similar Pattern Found</h3>
          <p className="text-xs text-gray-500">{pattern.date_range}</p>
        </div>
        
        <span className={`px-2 py-1 rounded-full text-xs font-semibold border ${getConfidenceColor()}`}>
          {confidencePercentage}% match
        </span>
      </div>

      {/* Description */}
      <p className="text-sm text-gray-700 mb-4 leading-relaxed">
        {pattern.description}
      </p>

      {/* Metric Values */}
      {Object.keys(pattern.metric_values).length > 0 && (
        <div className="border-t border-gray-100 pt-4">
          <h4 className="text-xs font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Metrics
          </h4>
          <dl className="grid grid-cols-2 gap-2">
            {Object.entries(pattern.metric_values).map(([key, value]) => (
              <div key={key} className="flex flex-col">
                <dt className="text-xs text-gray-500 capitalize">
                  {key.replace(/_/g, ' ')}
                </dt>
                <dd className="text-sm font-semibold text-gray-900">
                  {formatMetricValue(key, value)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
};

export default PatternCard;

