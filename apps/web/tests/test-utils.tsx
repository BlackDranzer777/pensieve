import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import type { ReactElement, ReactNode, JSX } from 'react';
import { MemoryRouter } from 'react-router-dom';

/**
 * Render a component inside the providers the app supplies at runtime.
 *
 * Retries are disabled so a test asserting the error state does not wait for
 * the retry schedule, and each call builds a fresh QueryClient so tests cannot
 * observe each other's cached data.
 */
export function renderWithProviders(
  ui: ReactElement,
  options: { route?: string; renderOptions?: Omit<RenderOptions, 'wrapper'> } = {},
): RenderResult & { queryClient: QueryClient } {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });

  function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter
          initialEntries={[options.route ?? '/']}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          {children}
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...options.renderOptions }),
    queryClient,
  };
}

/** A valid `HealthResponse` body, overridable per test. */
export function healthFixture(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    status: 'ok',
    version: '0.1.0',
    environment: 'test',
    processing_version: '1.0.0',
    timestamp: '2026-08-05T10:00:00Z',
    checks: [{ name: 'database', status: 'ok', detail: null }],
    ...overrides,
  };
}

/** Stub `fetch` with a JSON response. Returns the mock for assertions. */
export function mockFetchJson(
  body: unknown,
  init: { status?: number } = {},
): ReturnType<typeof vi.fn> {
  const mock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: init.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  globalThis.fetch = mock;
  return mock;
}

/** Stub `fetch` with a network-level failure. */
export function mockFetchNetworkError(): ReturnType<typeof vi.fn> {
  const mock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
  globalThis.fetch = mock;
  return mock;
}
