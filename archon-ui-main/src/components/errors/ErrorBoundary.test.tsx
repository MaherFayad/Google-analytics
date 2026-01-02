/**
 * Error Boundary Tests
 * 
 * Implements Task 6.2: Global Error Boundary Testing
 * 
 * Tests:
 * - Error catching and fallback UI
 * - Error logging
 * - Recovery/retry functionality
 * - Chart-specific error handling
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatErrorBoundary } from './ChatErrorBoundary';
import { ChartErrorBoundary } from './ChartErrorBoundary';

/**
 * Component that throws error on demand
 */
const ThrowError: React.FC<{ shouldThrow?: boolean; message?: string }> = ({
  shouldThrow = true,
  message = 'Test error',
}) => {
  if (shouldThrow) {
    throw new Error(message);
  }
  return <div>No error</div>;
};

/**
 * Malformed chart component for testing
 */
const MalformedChart: React.FC = () => {
  // Simulate chart rendering error
  throw new Error('Cannot read property "data" of undefined');
};

describe('ChatErrorBoundary', () => {
  // Suppress console.error for cleaner test output
  beforeEach(() => {
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('renders children when no error occurs', () => {
    render(
      <ChatErrorBoundary>
        <div>Test content</div>
      </ChatErrorBoundary>
    );

    expect(screen.getByText('Test content')).toBeInTheDocument();
  });

  it('renders fallback UI when error is caught', () => {
    render(
      <ChatErrorBoundary>
        <ThrowError message="Test error message" />
      </ChatErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText(/Test error message/)).toBeInTheDocument();
  });

  it('shows "Try Again" button in fallback UI', () => {
    render(
      <ChatErrorBoundary>
        <ThrowError />
      </ChatErrorBoundary>
    );

    const tryAgainButton = screen.getByRole('button', { name: /try again/i });
    expect(tryAgainButton).toBeInTheDocument();
  });

  it('resets error state when "Try Again" is clicked', () => {
    const { rerender } = render(
      <ChatErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ChatErrorBoundary>
    );

    // Error state shown
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    // Click try again
    const tryAgainButton = screen.getByRole('button', { name: /try again/i });
    fireEvent.click(tryAgainButton);

    // Re-render with no error
    rerender(
      <ChatErrorBoundary>
        <ThrowError shouldThrow={false} />
      </ChatErrorBoundary>
    );

    // Should show content now
    expect(screen.getByText('No error')).toBeInTheDocument();
  });

  it('calls onError callback when error is caught', () => {
    const onError = jest.fn();

    render(
      <ChatErrorBoundary onError={onError}>
        <ThrowError message="Callback test" />
      </ChatErrorBoundary>
    );

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'Callback test' }),
      expect.anything()
    );
  });

  it('toggles error details visibility', () => {
    render(
      <ChatErrorBoundary>
        <ThrowError message="Details test" />
      </ChatErrorBoundary>
    );

    // Initially details hidden
    expect(screen.queryByText('Technical Details')).not.toBeInTheDocument();

    // Click show details
    const showDetailsButton = screen.getByRole('button', { name: /show details/i });
    fireEvent.click(showDetailsButton);

    // Details now visible
    expect(screen.getByText('Technical Details')).toBeInTheDocument();
    expect(screen.getByText('Component Stack')).toBeInTheDocument();

    // Click hide details
    const hideDetailsButton = screen.getByRole('button', { name: /hide details/i });
    fireEvent.click(hideDetailsButton);

    // Details hidden again
    expect(screen.queryByText('Technical Details')).not.toBeInTheDocument();
  });

  it('identifies chart-specific errors', () => {
    render(
      <ChatErrorBoundary>
        <ThrowError message="ChartRenderer failed to render" />
      </ChatErrorBoundary>
    );

    expect(screen.getByText('Visualization Error')).toBeInTheDocument();
    expect(
      screen.getByText(/We encountered an error while rendering the chart/)
    ).toBeInTheDocument();
  });
});

describe('ChartErrorBoundary', () => {
  beforeEach(() => {
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('renders children when no error occurs', () => {
    render(
      <ChartErrorBoundary>
        <div>Chart content</div>
      </ChartErrorBoundary>
    );

    expect(screen.getByText('Chart content')).toBeInTheDocument();
  });

  it('renders fallback UI for chart errors', () => {
    render(
      <ChartErrorBoundary chartTitle="Test Chart">
        <MalformedChart />
      </ChartErrorBoundary>
    );

    expect(screen.getByText('Chart Rendering Failed')).toBeInTheDocument();
    expect(screen.getByText(/Test Chart could not be displayed/)).toBeInTheDocument();
  });

  it('shows "Show Data" button when chartData provided', () => {
    const chartData = {
      type: 'line',
      data: [
        { x: '2024-01-01', y: 100 },
        { x: '2024-01-02', y: 150 },
      ],
    };

    render(
      <ChartErrorBoundary chartData={chartData}>
        <MalformedChart />
      </ChartErrorBoundary>
    );

    expect(screen.getByRole('button', { name: /show data/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download json/i })).toBeInTheDocument();
  });

  it('toggles raw data display', () => {
    const chartData = {
      type: 'line',
      data: [
        { x: '2024-01-01', y: 100 },
        { x: '2024-01-02', y: 150 },
      ],
    };

    render(
      <ChartErrorBoundary chartData={chartData}>
        <MalformedChart />
      </ChartErrorBoundary>
    );

    // Initially data hidden
    expect(screen.queryByText('Raw Data')).not.toBeInTheDocument();

    // Click show data
    const showDataButton = screen.getByRole('button', { name: /show data/i });
    fireEvent.click(showDataButton);

    // Data now visible
    expect(screen.getByText('Raw Data')).toBeInTheDocument();
  });

  it('renders data as table when array provided', () => {
    const chartData = {
      type: 'line',
      data: [
        { date: '2024-01-01', sessions: 100 },
        { date: '2024-01-02', sessions: 150 },
      ],
    };

    render(
      <ChartErrorBoundary chartData={chartData}>
        <MalformedChart />
      </ChartErrorBoundary>
    );

    // Show data
    fireEvent.click(screen.getByRole('button', { name: /show data/i }));

    // Table headers
    expect(screen.getByText('DATE')).toBeInTheDocument();
    expect(screen.getByText('SESSIONS')).toBeInTheDocument();

    // Table data
    expect(screen.getByText('2024-01-01')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
  });

  it('calls onError callback when chart error is caught', () => {
    const onError = jest.fn();

    render(
      <ChartErrorBoundary onError={onError}>
        <MalformedChart />
      </ChartErrorBoundary>
    );

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({
        message: expect.stringContaining('Cannot read property'),
      })
    );
  });
});

describe('Error Boundary HOCs', () => {
  it('withChatErrorBoundary wraps component correctly', () => {
    const TestComponent: React.FC = () => <div>Wrapped component</div>;
    const WrappedComponent = withChatErrorBoundary(TestComponent);

    render(<WrappedComponent />);

    expect(screen.getByText('Wrapped component')).toBeInTheDocument();
  });

  it('withChartErrorBoundary wraps component correctly', () => {
    const TestChart: React.FC = () => <div>Chart component</div>;
    const WrappedChart = withChartErrorBoundary(TestChart);

    render(<WrappedChart />);

    expect(screen.getByText('Chart component')).toBeInTheDocument();
  });
});

