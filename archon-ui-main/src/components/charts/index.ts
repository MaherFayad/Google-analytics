/**
 * Charts Module Exports
 * 
 * Central export point for all chart components.
 */

export { ChartRenderer, MultiChartRenderer } from './ChartRenderer';
export type { ChartRendererProps } from './ChartRenderer';

export { 
  TypeSafeChartRenderer, 
  ChartGrid 
} from './TypeSafeChartRenderer';

// Task 6.2: Safe Chart Renderer with Error Boundary
export { SafeChartRenderer } from './SafeChartRenderer';
export type { SafeChartRendererProps } from './SafeChartRenderer';

export default ChartRenderer;

