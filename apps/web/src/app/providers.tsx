import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode, type JSX } from 'react';

import { ApiError } from '@/lib/api-error';

/**
 * Create the query client.
 *
 * Built inside a component (via `useState`) rather than at module scope so
 * each test gets an isolated cache — a shared module-level client leaks state
 * between tests and produces confusing order-dependent failures.
 */
function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // Retrying a 4xx or a schema mismatch just repeats the same failure
          // more slowly. Only transient problems are worth another attempt.
          if (error instanceof ApiError) {
            if (error.kind === 'schema') return false;
            if (error.status && error.status >= 400 && error.status < 500) return false;
          }
          return failureCount < 2;
        },
      },
    },
  });
}

export function AppProviders({ children }: { children: ReactNode }): JSX.Element {
  const [queryClient] = useState(createQueryClient);
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
