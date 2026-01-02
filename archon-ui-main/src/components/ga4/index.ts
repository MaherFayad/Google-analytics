/**
 * GA4 Components Index
 * 
 * Centralizes exports for GA4 analytics components.
 */

export { MetricCard } from './MetricCard';
export { PatternCard } from './PatternCard';
export { QueryInput } from './QueryInput';
export { AnalyticsHeader } from './AnalyticsHeader';
export { ConfidenceBadge } from './ConfidenceBadge';
export { ConnectionStatus } from './ConnectionStatus';
export { QueueStatusBanner } from './QueueStatusBanner';

// Task P0-8: Report Export & Power User Features
export { ReportToolbar } from './ReportToolbar';
export type { ReportToolbarProps } from './ReportToolbar';
export { ComparisonChart, transformToComparisonData } from './ComparisonChart';
export type { ComparisonChartProps, ComparisonDataPoint } from './ComparisonChart';

// Task 5.3: Chat Interface & Stream Hook
export { ChatInterface } from './ChatInterface';
export type { ChatInterfaceProps } from './ChatInterface';

// Task 10.3: OAuth Connection Status UI
export { GA4ConnectionCard } from './GA4ConnectionCard';

// Task P0-37: Chart Accessibility (WCAG 2.1 AA Compliance)
export { AccessibleChartRenderer } from './AccessibleChartRenderer';
export type { AccessibleChartRendererProps } from './AccessibleChartRenderer';

// Task 6.1: History Sidebar & Navigation
export { HistorySidebar } from './HistorySidebar';
export type { HistorySidebarProps } from './HistorySidebar';

