# Error Boundary Implementation Guide

**Implements Task 6.2: Global Error Boundary**

This guide explains how to use Error Boundaries to gracefully handle errors in the GA4 Analytics Chat application.

## Table of Contents

1. [Overview](#overview)
2. [Available Error Boundaries](#available-error-boundaries)
3. [Usage Examples](#usage-examples)
4. [Best Practices](#best-practices)
5. [Error Logging](#error-logging)
6. [Testing](#testing)

---

## Overview

Error Boundaries are React components that catch JavaScript errors in their child component tree and display a fallback UI instead of crashing the entire application.

**Benefits:**
- ✅ Prevents UI crashes from malformed data
- ✅ Shows user-friendly error messages
- ✅ Allows error recovery without page reload
- ✅ Logs errors for debugging
- ✅ Graceful degradation for chart rendering failures

---

## Available Error Boundaries

### 1. ChatErrorBoundary

General-purpose error boundary for chat interface components.

**Use for:**
- Chat interface errors
- Message display issues
- Streaming connection errors
- General UI crashes

**Location:** `src/components/errors/ChatErrorBoundary.tsx`

### 2. ChartErrorBoundary

Specialized error boundary for chart rendering with fallback to raw data.

**Use for:**
- Chart rendering failures
- Malformed chart data
- Recharts component errors

**Location:** `src/components/errors/ChartErrorBoundary.tsx`

---

## Usage Examples

### Example 1: Wrap Chat Interface

```tsx
import { ChatInterface } from '@/components/ga4/ChatInterface';
import { ChatErrorBoundary } from '@/components/errors';

export default function AnalyticsPage() {
  return (
    <ChatErrorBoundary
      onError={(error, errorInfo) => {
        console.error('Chat error:', error);
        // Send to error tracking service
      }}
    >
      <ChatInterface />
    </ChatErrorBoundary>
  );
}
```

### Example 2: Wrap Individual Charts

```tsx
import { ChartRenderer } from '@/components/charts/ChartRenderer';
import { ChartErrorBoundary } from '@/components/errors';

function Dashboard({ charts }) {
  return (
    <div>
      {charts.map((chart) => (
        <ChartErrorBoundary
          key={chart.id}
          chartData={chart}
          chartTitle={chart.title}
        >
          <ChartRenderer config={chart} />
        </ChartErrorBoundary>
      ))}
    </div>
  );
}
```

### Example 3: Use Safe Chart Renderer (Recommended)

```tsx
import { SafeChartRenderer } from '@/components/charts/SafeChartRenderer';

function Report({ chartConfig }) {
  return (
    <SafeChartRenderer
      config={chartConfig}
      onError={(error) => {
        // Optional: log chart-specific errors
        console.warn('Chart failed to render:', error);
      }}
    />
  );
}
```

### Example 4: Use HOC Wrapper

```tsx
import { withChatErrorBoundary } from '@/components/errors';
import { ChatInterface } from '@/components/ga4/ChatInterface';

// Wrap component with error boundary
const SafeChatInterface = withChatErrorBoundary(ChatInterface, {
  onError: (error) => {
    console.error('Chat error:', error);
  },
});

export default function Page() {
  return <SafeChatInterface />;
}
```

---

## Best Practices

### 1. **Layer Error Boundaries**

Place error boundaries at multiple levels for fine-grained error handling:

```tsx
<ChatErrorBoundary>              {/* Top-level: whole chat */}
  <ChatLayout>
    <HistorySidebar />
    
    <ChatInterface>
      {messages.map(msg => (
        <ChartErrorBoundary key={msg.id}>  {/* Chart-level */}
          <ChartRenderer config={msg.chart} />
        </ChartErrorBoundary>
      ))}
    </ChatInterface>
  </ChatLayout>
</ChatErrorBoundary>
```

### 2. **Always Provide onError Handler**

Log errors for debugging and monitoring:

```tsx
<ChatErrorBoundary
  onError={(error, errorInfo) => {
    // Development: console
    if (process.env.NODE_ENV === 'development') {
      console.error('Error:', error);
      console.error('Component stack:', errorInfo.componentStack);
    }
    
    // Production: send to Sentry/etc
    if (process.env.NODE_ENV === 'production') {
      Sentry.captureException(error, {
        contexts: {
          react: { componentStack: errorInfo.componentStack },
        },
      });
    }
  }}
>
  <YourComponent />
</ChatErrorBoundary>
```

### 3. **Show Fallback Data**

For charts, always pass `chartData` so users can see raw data if visualization fails:

```tsx
<ChartErrorBoundary
  chartData={config}
  chartTitle={config.title}
>
  <ChartRenderer config={config} />
</ChartErrorBoundary>
```

### 4. **Test Error Scenarios**

Create test components that throw errors to verify error boundaries work:

```tsx
// Test component
const ThrowError = () => {
  throw new Error('Test error');
};

// Test in development
<ChatErrorBoundary>
  <ThrowError />
</ChatErrorBoundary>
```

### 5. **Don't Overuse**

Error boundaries have overhead. Use them strategically:

✅ **DO**: Wrap major sections (pages, chat interface, chart grids)
❌ **DON'T**: Wrap every single small component

---

## Error Logging

### Development Mode

Errors are logged to console with full stack traces:

```
ChatErrorBoundary caught error: Error: Cannot read property 'data'
Error info: { componentStack: "..." }
Component stack: at ChartRenderer (...)
```

### Production Mode

Errors should be sent to an error tracking service:

```tsx
import * as Sentry from '@sentry/react';

<ChatErrorBoundary
  onError={(error, errorInfo) => {
    Sentry.captureException(error, {
      contexts: {
        react: {
          componentStack: errorInfo.componentStack,
        },
      },
      tags: {
        component: 'chat-interface',
      },
    });
  }}
>
  <ChatInterface />
</ChatErrorBoundary>
```

---

## Testing

### Unit Tests

Test error boundaries with components that throw errors:

```tsx
import { render, screen } from '@testing-library/react';
import { ChatErrorBoundary } from '@/components/errors';

const ThrowError = () => {
  throw new Error('Test error');
};

test('shows fallback UI on error', () => {
  render(
    <ChatErrorBoundary>
      <ThrowError />
    </ChatErrorBoundary>
  );
  
  expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  expect(screen.getByText(/Test error/)).toBeInTheDocument();
});
```

### Integration Tests

Test that error boundaries don't interfere with normal operation:

```tsx
test('renders children when no error', () => {
  render(
    <ChatErrorBoundary>
      <div>Normal content</div>
    </ChatErrorBoundary>
  );
  
  expect(screen.getByText('Normal content')).toBeInTheDocument();
});
```

### Manual Testing

**Test chart errors:**
1. Provide malformed chart config
2. Verify fallback UI shows
3. Verify "Show Data" button works
4. Verify JSON download works

**Test chat errors:**
1. Simulate API failure
2. Verify error message shows
3. Verify "Try Again" button works
4. Verify error doesn't crash app

---

## Common Error Scenarios

### 1. Malformed Chart Data

**Error:**
```
TypeError: Cannot read property 'data' of undefined
```

**Solution:**
- ChartErrorBoundary catches it
- Shows raw data table
- Allows JSON download

### 2. Streaming Connection Failure

**Error:**
```
Error: SSE connection lost
```

**Solution:**
- ChatErrorBoundary catches it
- Shows retry button
- Logs error for debugging

### 3. Invalid Report Structure

**Error:**
```
TypeError: report.charts.map is not a function
```

**Solution:**
- ChatErrorBoundary catches it
- Shows error message
- Allows recovery

---

## Troubleshooting

### Error Boundary Not Catching Errors

**Problem:** Error still crashes the app

**Solutions:**
1. Error boundaries don't catch:
   - Errors in event handlers (use try/catch)
   - Async errors (use try/catch)
   - Server-side rendering errors

2. Ensure error is thrown during render:
```tsx
// ✅ CAUGHT by error boundary
const Component = () => {
  throw new Error('Render error');
};

// ❌ NOT caught by error boundary
const Component = () => {
  const handleClick = () => {
    throw new Error('Click error');
  };
  return <button onClick={handleClick}>Click</button>;
};
```

### Fallback UI Not Showing

**Problem:** Blank screen instead of fallback UI

**Solutions:**
1. Check error boundary is parent of failing component
2. Verify fallback UI code doesn't have errors
3. Check console for nested errors

---

## Further Reading

- [React Error Boundaries Docs](https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary)
- [Error Boundary Best Practices](https://kentcdodds.com/blog/use-react-error-boundary-to-handle-errors-in-react)
- Task 6.2 Implementation Details

---

**Last Updated:** January 2, 2026  
**Maintainer:** Archon Development Team

