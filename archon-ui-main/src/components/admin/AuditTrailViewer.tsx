/**
 * Audit Trail Viewer Component
 * 
 * Implements Task P0-44: Admin Audit Trail API for Data Lineage
 * 
 * Visualizes complete data lineage from GA4 API → embeddings → LLM → report.
 * 
 * Features:
 * - Visual timeline of data flow
 * - Expandable step details
 * - Validation issue highlighting
 * - JSON export
 * - Performance metrics
 * 
 * Usage:
 *   <AuditTrailViewer reportId="report-123" />
 */

'use client';

import React, { useState, useEffect } from 'react';
import { 
  CheckCircle, 
  XCircle, 
  Clock, 
  Database, 
  Sparkles, 
  Search, 
  FileText,
  Download,
  ChevronDown,
  ChevronRight,
  AlertTriangle
} from 'lucide-react';

// ============================================================================
// Type Definitions
// ============================================================================

interface GA4APIRequest {
  endpoint: string;
  request_params: Record<string, any>;
  response_time_ms: number;
  cached: boolean;
  timestamp: string;
  status: string;
  error_message?: string;
}

interface RawMetric {
  id: number;
  metric_date: string;
  dimension_values: Record<string, string>;
  metric_values: Record<string, number>;
  property_id: string;
}

interface EmbeddingUsed {
  id: string;
  similarity: number;
  content: string;
  chunk_metadata: Record<string, any>;
  timestamp_created: string;
}

interface LLMInteraction {
  model: string;
  prompt: string;
  prompt_tokens: number;
  response: string;
  response_tokens: number;
  latency_ms: number;
  temperature: number;
  timestamp: string;
}

interface ValidationResults {
  grounding_score: number;
  citation_accuracy: number;
  ungrounded_claims: string[];
  confidence_score: number;
  validation_timestamp: string;
}

interface DataLineageStep {
  step_number: number;
  step_name: string;
  input_data: Record<string, any>;
  output_data: Record<string, any>;
  duration_ms: number;
  timestamp: string;
  metadata?: Record<string, any>;
}

interface AuditTrail {
  report_id: string;
  query: string;
  tenant_id: string;
  user_id: string;
  created_at: string;
  ga4_api_request?: GA4APIRequest;
  raw_metrics: RawMetric[];
  embeddings_used: EmbeddingUsed[];
  llm_interaction?: LLMInteraction;
  validation_results?: ValidationResults;
  lineage_steps: DataLineageStep[];
  total_duration_ms: number;
  cache_hits: Record<string, boolean>;
  metadata: Record<string, any>;
}

export interface AuditTrailViewerProps {
  reportId: string;
  onClose?: () => void;
}

// ============================================================================
// Sub-Components
// ============================================================================

const TimelineStep: React.FC<{
  step: DataLineageStep;
  icon: React.ReactNode;
  isExpanded: boolean;
  onToggle: () => void;
}> = ({ step, icon, isExpanded, onToggle }) => {
  return (
    <div className="relative pl-8 pb-8 border-l-2 border-gray-300 last:border-0">
      {/* Timeline node */}
      <div className="absolute left-0 top-0 -translate-x-1/2 w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center border-2 border-blue-500">
        {icon}
      </div>
      
      {/* Step content */}
      <div className="ml-4">
        <button
          onClick={onToggle}
          className="flex items-center gap-2 text-lg font-semibold text-gray-900 hover:text-blue-600 transition-colors"
        >
          {isExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
          {step.step_name}
          <span className="ml-auto text-sm text-gray-500 font-normal">
            {step.duration_ms}ms
          </span>
        </button>
        
        {isExpanded && (
          <div className="mt-3 space-y-2">
            <div className="bg-gray-50 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-700 mb-2">Input Data</h4>
              <pre className="text-xs bg-white p-2 rounded border overflow-x-auto">
                {JSON.stringify(step.input_data, null, 2)}
              </pre>
            </div>
            
            <div className="bg-gray-50 rounded-lg p-3">
              <h4 className="text-sm font-medium text-gray-700 mb-2">Output Data</h4>
              <pre className="text-xs bg-white p-2 rounded border overflow-x-auto">
                {JSON.stringify(step.output_data, null, 2)}
              </pre>
            </div>
            
            {step.metadata && Object.keys(step.metadata).length > 0 && (
              <div className="bg-gray-50 rounded-lg p-3">
                <h4 className="text-sm font-medium text-gray-700 mb-2">Metadata</h4>
                <pre className="text-xs bg-white p-2 rounded border overflow-x-auto">
                  {JSON.stringify(step.metadata, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

const ValidationPanel: React.FC<{ validation: ValidationResults }> = ({ validation }) => {
  const hasIssues = validation.ungrounded_claims.length > 0;
  
  return (
    <div className={`rounded-lg p-4 ${hasIssues ? 'bg-red-50 border border-red-200' : 'bg-green-50 border border-green-200'}`}>
      <div className="flex items-center gap-2 mb-3">
        {hasIssues ? (
          <XCircle className="h-5 w-5 text-red-600" />
        ) : (
          <CheckCircle className="h-5 w-5 text-green-600" />
        )}
        <h3 className="text-lg font-semibold">
          {hasIssues ? 'Validation Issues Found' : 'Validation Passed'}
        </h3>
      </div>
      
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div>
          <p className="text-sm text-gray-600">Grounding Score</p>
          <p className="text-2xl font-bold">{(validation.grounding_score * 100).toFixed(1)}%</p>
        </div>
        <div>
          <p className="text-sm text-gray-600">Citation Accuracy</p>
          <p className="text-2xl font-bold">{(validation.citation_accuracy * 100).toFixed(1)}%</p>
        </div>
        <div>
          <p className="text-sm text-gray-600">Confidence</p>
          <p className="text-2xl font-bold">{(validation.confidence_score * 100).toFixed(1)}%</p>
        </div>
      </div>
      
      {hasIssues && (
        <div className="mt-3 space-y-2">
          <h4 className="text-sm font-semibold text-red-800 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Ungrounded Claims ({validation.ungrounded_claims.length})
          </h4>
          <ul className="list-disc list-inside space-y-1">
            {validation.ungrounded_claims.map((claim, idx) => (
              <li key={idx} className="text-sm text-red-700">{claim}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

// ============================================================================
// Main Component
// ============================================================================

export const AuditTrailViewer: React.FC<AuditTrailViewerProps> = ({ reportId, onClose }) => {
  const [auditTrail, setAuditTrail] = useState<AuditTrail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set([1]));

  useEffect(() => {
    fetchAuditTrail();
  }, [reportId]);

  const fetchAuditTrail = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // TODO: Replace with actual API call
      const response = await fetch(`/api/v1/admin/reports/${reportId}/audit_trail`);
      
      if (!response.ok) {
        throw new Error('Failed to fetch audit trail');
      }
      
      const data = await response.json();
      setAuditTrail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const toggleStep = (stepNumber: number) => {
    setExpandedSteps(prev => {
      const next = new Set(prev);
      if (next.has(stepNumber)) {
        next.delete(stepNumber);
      } else {
        next.add(stepNumber);
      }
      return next;
    });
  };

  const expandAll = () => {
    if (auditTrail) {
      setExpandedSteps(new Set(auditTrail.lineage_steps.map(s => s.step_number)));
    }
  };

  const collapseAll = () => {
    setExpandedSteps(new Set());
  };

  const exportAuditTrail = async () => {
    try {
      const response = await fetch(`/api/v1/admin/reports/${reportId}/audit_trail/export`, {
        method: 'POST'
      });
      
      if (!response.ok) {
        throw new Error('Export failed');
      }
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_trail_${reportId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export error:', err);
      alert('Failed to export audit trail');
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading audit trail...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <h3 className="text-red-800 font-semibold mb-2">Error Loading Audit Trail</h3>
        <p className="text-red-700">{error}</p>
        <button
          onClick={fetchAuditTrail}
          className="mt-3 px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    );
  }

  // No data state
  if (!auditTrail) {
    return (
      <div className="text-center py-8 text-gray-600">
        <p>No audit trail data available</p>
      </div>
    );
  }

  const stepIcons = {
    1: <Database className="h-5 w-5 text-blue-600" />,
    2: <Sparkles className="h-5 w-5 text-purple-600" />,
    3: <Search className="h-5 w-5 text-green-600" />,
    4: <FileText className="h-5 w-5 text-orange-600" />,
  };

  return (
    <div className="bg-white rounded-lg shadow-lg max-w-5xl mx-auto">
      {/* Header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Audit Trail</h2>
            <p className="text-sm text-gray-600 mt-1">
              Report ID: <span className="font-mono">{reportId}</span>
            </p>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={exportAuditTrail}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 flex items-center gap-2"
            >
              <Download className="h-4 w-4" />
              Export JSON
            </button>
            {onClose && (
              <button
                onClick={onClose}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300"
              >
                Close
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Summary */}
      <div className="px-6 py-4 bg-gray-50 border-b">
        <div className="grid grid-cols-4 gap-4">
          <div>
            <p className="text-sm text-gray-600">Query</p>
            <p className="font-medium">{auditTrail.query}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Total Duration</p>
            <p className="font-medium flex items-center gap-1">
              <Clock className="h-4 w-4" />
              {auditTrail.total_duration_ms}ms
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Created</p>
            <p className="font-medium">
              {new Date(auditTrail.created_at).toLocaleString()}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Cache Hits</p>
            <p className="font-medium">
              {Object.values(auditTrail.cache_hits).filter(Boolean).length} / {Object.keys(auditTrail.cache_hits).length}
            </p>
          </div>
        </div>
      </div>

      {/* Validation Results */}
      {auditTrail.validation_results && (
        <div className="px-6 py-4 border-b">
          <ValidationPanel validation={auditTrail.validation_results} />
        </div>
      )}

      {/* Timeline Controls */}
      <div className="px-6 py-3 border-b bg-gray-50 flex items-center justify-between">
        <h3 className="text-lg font-semibold">Data Lineage Timeline</h3>
        <div className="flex gap-2">
          <button
            onClick={expandAll}
            className="text-sm px-3 py-1 bg-gray-200 rounded hover:bg-gray-300"
          >
            Expand All
          </button>
          <button
            onClick={collapseAll}
            className="text-sm px-3 py-1 bg-gray-200 rounded hover:bg-gray-300"
          >
            Collapse All
          </button>
        </div>
      </div>

      {/* Timeline */}
      <div className="px-6 py-6">
        {auditTrail.lineage_steps.map((step) => (
          <TimelineStep
            key={step.step_number}
            step={step}
            icon={stepIcons[step.step_number as keyof typeof stepIcons] || <FileText className="h-5 w-5" />}
            isExpanded={expandedSteps.has(step.step_number)}
            onToggle={() => toggleStep(step.step_number)}
          />
        ))}
      </div>

      {/* Raw Data Sections */}
      <div className="px-6 py-4 border-t space-y-4">
        {/* Embeddings Used */}
        {auditTrail.embeddings_used.length > 0 && (
          <details className="border rounded-lg">
            <summary className="cursor-pointer p-4 font-semibold hover:bg-gray-50">
              Embeddings Used ({auditTrail.embeddings_used.length})
            </summary>
            <div className="p-4 space-y-3 border-t">
              {auditTrail.embeddings_used.map((emb, idx) => (
                <div key={emb.id} className="border-l-4 border-purple-500 pl-4">
                  <div className="flex justify-between mb-2">
                    <span className="text-sm font-medium">Similarity: {(emb.similarity * 100).toFixed(1)}%</span>
                    <span className="text-xs text-gray-500">{emb.id}</span>
                  </div>
                  <p className="text-sm text-gray-700">{emb.content}</p>
                </div>
              ))}
            </div>
          </details>
        )}

        {/* LLM Interaction */}
        {auditTrail.llm_interaction && (
          <details className="border rounded-lg">
            <summary className="cursor-pointer p-4 font-semibold hover:bg-gray-50">
              LLM Interaction ({auditTrail.llm_interaction.model})
            </summary>
            <div className="p-4 space-y-3 border-t">
              <div>
                <h4 className="font-medium mb-2">Prompt ({auditTrail.llm_interaction.prompt_tokens} tokens)</h4>
                <pre className="text-xs bg-gray-50 p-3 rounded border overflow-x-auto max-h-64">
                  {auditTrail.llm_interaction.prompt}
                </pre>
              </div>
              <div>
                <h4 className="font-medium mb-2">Response ({auditTrail.llm_interaction.response_tokens} tokens)</h4>
                <pre className="text-xs bg-gray-50 p-3 rounded border overflow-x-auto max-h-64">
                  {auditTrail.llm_interaction.response}
                </pre>
              </div>
            </div>
          </details>
        )}
      </div>
    </div>
  );
};

export default AuditTrailViewer;

