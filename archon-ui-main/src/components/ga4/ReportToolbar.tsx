/**
 * Report Toolbar Component
 * 
 * Implements Task P0-8: Report Export & Power User Features
 * 
 * Features:
 * - CSV/Excel export buttons
 * - Share link generation
 * - Print report
 * - Download as PDF (future)
 * 
 * Usage:
 *   <ReportToolbar reportId="report_123" onExport={handleExport} />
 */

'use client';

import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  DownloadIcon,
  ShareIcon,
  PrinterIcon,
  FileTextIcon,
  FileSpreadsheetIcon,
} from 'lucide-react';

export interface ReportToolbarProps {
  reportId: string;
  onExport?: (format: 'csv' | 'excel' | 'pdf') => void;
  onShare?: () => void;
  onPrint?: () => void;
  className?: string;
}

export const ReportToolbar: React.FC<ReportToolbarProps> = ({
  reportId,
  onExport,
  onShare,
  onPrint,
  className = '',
}) => {
  const [isExporting, setIsExporting] = useState(false);
  const [isSharing, setIsSharing] = useState(false);

  const handleExportCSV = async () => {
    try {
      setIsExporting(true);
      
      if (onExport) {
        onExport('csv');
      } else {
        // Default: Download via API
        const response = await fetch(`/api/v1/export/reports/${reportId}/csv`);
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `report_${reportId}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('CSV export failed:', error);
      alert('Failed to export CSV. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportExcel = async () => {
    try {
      setIsExporting(true);
      
      if (onExport) {
        onExport('excel');
      } else {
        const response = await fetch(`/api/v1/export/reports/${reportId}/excel`);
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `report_${reportId}.xlsx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      }
    } catch (error) {
      console.error('Excel export failed:', error);
      alert('Failed to export Excel. Please try again.');
    } finally {
      setIsExporting(false);
    }
  };

  const handleShare = async () => {
    try {
      setIsSharing(true);
      
      if (onShare) {
        onShare();
      } else {
        // Default: Create share link via API
        const response = await fetch('/api/v1/sharing/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            report_id: reportId,
            expires_in_hours: 24,
            allow_export: false,
          }),
        });
        
        const data = await response.json();
        
        if (data.success) {
          // Copy to clipboard
          await navigator.clipboard.writeText(data.share_url);
          alert(`Share link copied to clipboard!\nExpires: ${new Date(data.expires_at).toLocaleString()}`);
        } else {
          throw new Error(data.message || 'Failed to create share link');
        }
      }
    } catch (error) {
      console.error('Share failed:', error);
      alert('Failed to create share link. Please try again.');
    } finally {
      setIsSharing(false);
    }
  };

  const handlePrint = () => {
    if (onPrint) {
      onPrint();
    } else {
      window.print();
    }
  };

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Export Dropdown */}
      <div className="flex items-center gap-1 border rounded-md">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleExportCSV}
          disabled={isExporting}
          title="Export as CSV"
        >
          <FileTextIcon className="w-4 h-4 mr-1" />
          CSV
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleExportExcel}
          disabled={isExporting}
          title="Export as Excel"
        >
          <FileSpreadsheetIcon className="w-4 h-4 mr-1" />
          Excel
        </Button>
      </div>

      {/* Share Button */}
      <Button
        variant="outline"
        size="sm"
        onClick={handleShare}
        disabled={isSharing}
        title="Share report"
      >
        <ShareIcon className="w-4 h-4 mr-1" />
        Share
      </Button>

      {/* Print Button */}
      <Button
        variant="outline"
        size="sm"
        onClick={handlePrint}
        title="Print report"
      >
        <PrinterIcon className="w-4 h-4 mr-1" />
        Print
      </Button>

      {/* Loading indicator */}
      {(isExporting || isSharing) && (
        <span className="text-sm text-gray-500">
          {isExporting ? 'Exporting...' : 'Creating share link...'}
        </span>
      )}
    </div>
  );
};

export default ReportToolbar;

