/**
 * Keyboard Navigation Hook for Charts
 * 
 * Implements Task P0-37: Chart Accessibility (WCAG 2.1 AA Compliance)
 * 
 * Features:
 * - Keyboard navigation through chart data points
 * - Screen reader announcements
 * - Focus management
 * - WCAG 2.1 keyboard interaction patterns
 * 
 * Keyboard Controls:
 * - Arrow Right/Left: Navigate between data points
 * - Home/End: Jump to first/last data point
 * - Enter/Space: Announce current data point details
 * - Escape: Exit navigation mode
 * 
 * ARIA Live Regions:
 * - Announces focused data point values
 * - Provides context about position (e.g., "Point 3 of 10")
 */

'use client';

import { useState, useCallback, useEffect, useRef } from 'react';

export interface DataPoint {
  [key: string]: any;
}

export interface KeyboardNavigationOptions {
  /**
   * Data points to navigate through
   */
  data: DataPoint[];
  
  /**
   * Keys to announce when focusing a point
   */
  announceKeys?: string[];
  
  /**
   * Custom formatter for announcements
   */
  formatAnnouncement?: (point: DataPoint, index: number, total: number) => string;
  
  /**
   * Callback when focused point changes
   */
  onFocusChange?: (index: number, point: DataPoint) => void;
  
  /**
   * Enable automatic announcements (default: true)
   */
  enableAnnouncements?: boolean;
}

export interface KeyboardNavigationResult {
  /**
   * Current focused index (-1 if no focus)
   */
  focusedIndex: number;
  
  /**
   * Currently focused data point (null if no focus)
   */
  focusedPoint: DataPoint | null;
  
  /**
   * Keyboard event handler
   */
  handleKeyDown: (event: React.KeyboardEvent) => void;
  
  /**
   * Focus a specific index programmatically
   */
  setFocusedIndex: (index: number) => void;
  
  /**
   * Clear focus
   */
  clearFocus: () => void;
  
  /**
   * Current announcement text (for screen readers)
   */
  announcement: string;
  
  /**
   * Whether navigation is active
   */
  isNavigating: boolean;
}

/**
 * Custom hook for keyboard navigation in charts.
 * 
 * @example
 * ```tsx
 * function MyChart({ data }) {
 *   const { focusedIndex, handleKeyDown, announcement } = useKeyboardChartNavigation({
 *     data,
 *     announceKeys: ['date', 'value'],
 *   });
 *   
 *   return (
 *     <div 
 *       tabIndex={0} 
 *       onKeyDown={handleKeyDown}
 *       role="img"
 *       aria-label="Sales over time chart"
 *     >
 *       <span className="sr-only" role="status" aria-live="polite" aria-atomic="true">
 *         {announcement}
 *       </span>
 *       
 *       <LineChart data={data}>
 *         {data.map((point, index) => (
 *           <DataPoint 
 *             key={index}
 *             isFocused={index === focusedIndex}
 *             {...point}
 *           />
 *         ))}
 *       </LineChart>
 *     </div>
 *   );
 * }
 * ```
 */
export function useKeyboardChartNavigation(
  options: KeyboardNavigationOptions
): KeyboardNavigationResult {
  const {
    data,
    announceKeys,
    formatAnnouncement,
    onFocusChange,
    enableAnnouncements = true,
  } = options;
  
  const [focusedIndex, setFocusedIndexState] = useState<number>(-1);
  const [announcement, setAnnouncement] = useState<string>('');
  const [isNavigating, setIsNavigating] = useState<boolean>(false);
  
  // Keep track of announcement timeout to avoid spamming
  const announcementTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  /**
   * Update focused index and trigger announcement.
   */
  const setFocusedIndex = useCallback((index: number) => {
    if (index < -1 || index >= data.length) {
      return; // Invalid index
    }
    
    setFocusedIndexState(index);
    setIsNavigating(index >= 0);
    
    // Trigger focus change callback
    if (index >= 0 && onFocusChange) {
      onFocusChange(index, data[index]);
    }
    
    // Generate announcement
    if (index >= 0 && enableAnnouncements) {
      const announcementText = formatAnnouncement
        ? formatAnnouncement(data[index], index, data.length)
        : generateDefaultAnnouncement(data[index], index, data.length, announceKeys);
      
      // Debounce announcements
      if (announcementTimeoutRef.current) {
        clearTimeout(announcementTimeoutRef.current);
      }
      
      announcementTimeoutRef.current = setTimeout(() => {
        setAnnouncement(announcementText);
      }, 100); // Small delay to avoid rapid-fire announcements
    } else {
      setAnnouncement('');
    }
  }, [data, announceKeys, formatAnnouncement, onFocusChange, enableAnnouncements]);
  
  /**
   * Clear focus.
   */
  const clearFocus = useCallback(() => {
    setFocusedIndex(-1);
  }, [setFocusedIndex]);
  
  /**
   * Navigate to next data point.
   */
  const navigateNext = useCallback(() => {
    if (focusedIndex < data.length - 1) {
      setFocusedIndex(focusedIndex + 1);
    }
  }, [focusedIndex, data.length, setFocusedIndex]);
  
  /**
   * Navigate to previous data point.
   */
  const navigatePrevious = useCallback(() => {
    if (focusedIndex > 0) {
      setFocusedIndex(focusedIndex - 1);
    } else if (focusedIndex === -1 && data.length > 0) {
      // Start navigation from the beginning
      setFocusedIndex(0);
    }
  }, [focusedIndex, data.length, setFocusedIndex]);
  
  /**
   * Jump to first data point.
   */
  const navigateFirst = useCallback(() => {
    if (data.length > 0) {
      setFocusedIndex(0);
    }
  }, [data.length, setFocusedIndex]);
  
  /**
   * Jump to last data point.
   */
  const navigateLast = useCallback(() => {
    if (data.length > 0) {
      setFocusedIndex(data.length - 1);
    }
  }, [data.length, setFocusedIndex]);
  
  /**
   * Keyboard event handler.
   */
  const handleKeyDown = useCallback((event: React.KeyboardEvent) => {
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        event.preventDefault();
        navigateNext();
        break;
      
      case 'ArrowLeft':
      case 'ArrowUp':
        event.preventDefault();
        navigatePrevious();
        break;
      
      case 'Home':
        event.preventDefault();
        navigateFirst();
        break;
      
      case 'End':
        event.preventDefault();
        navigateLast();
        break;
      
      case 'Enter':
      case ' ': // Space
        event.preventDefault();
        // Re-announce current point
        if (focusedIndex >= 0) {
          const announcementText = formatAnnouncement
            ? formatAnnouncement(data[focusedIndex], focusedIndex, data.length)
            : generateDefaultAnnouncement(data[focusedIndex], focusedIndex, data.length, announceKeys);
          setAnnouncement(announcementText);
        }
        break;
      
      case 'Escape':
        event.preventDefault();
        clearFocus();
        break;
      
      default:
        // Ignore other keys
        break;
    }
  }, [
    focusedIndex,
    data,
    announceKeys,
    formatAnnouncement,
    navigateNext,
    navigatePrevious,
    navigateFirst,
    navigateLast,
    clearFocus,
  ]);
  
  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (announcementTimeoutRef.current) {
        clearTimeout(announcementTimeoutRef.current);
      }
    };
  }, []);
  
  // Reset focus when data changes
  useEffect(() => {
    if (focusedIndex >= data.length) {
      clearFocus();
    }
  }, [data.length, focusedIndex, clearFocus]);
  
  return {
    focusedIndex,
    focusedPoint: focusedIndex >= 0 ? data[focusedIndex] : null,
    handleKeyDown,
    setFocusedIndex,
    clearFocus,
    announcement,
    isNavigating,
  };
}

/**
 * Generate default announcement text for a data point.
 */
function generateDefaultAnnouncement(
  point: DataPoint,
  index: number,
  total: number,
  keys?: string[]
): string {
  const position = `Point ${index + 1} of ${total}`;
  
  if (!keys || keys.length === 0) {
    // Announce all keys if none specified
    keys = Object.keys(point);
  }
  
  const values = keys
    .filter(key => point[key] !== undefined && point[key] !== null)
    .map(key => {
      const value = point[key];
      const formattedValue = formatValue(value);
      return `${key}: ${formattedValue}`;
    })
    .join(', ');
  
  return `${position}. ${values}`;
}

/**
 * Format a value for screen reader announcement.
 */
function formatValue(value: any): string {
  if (typeof value === 'number') {
    // Format numbers with commas
    return value.toLocaleString();
  } else if (typeof value === 'boolean') {
    return value ? 'yes' : 'no';
  } else if (value === null || value === undefined) {
    return 'no data';
  } else {
    return String(value);
  }
}

/**
 * Helper hook for screen reader only content.
 * 
 * Returns className for visually hidden but screen-reader-accessible content.
 */
export function useScreenReaderOnly() {
  return 'sr-only absolute w-px h-px p-0 -m-px overflow-hidden whitespace-nowrap border-0';
}

