import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { apiFetch } from '@/lib/api-client';
import { healthResponseSchema, type HealthResponse } from '@/types/health';

export const healthQueryKey = ['health'] as const;

/**
 * Poll the API health endpoint.
 *
 * Polling (rather than a one-shot query) means the status indicator in the top
 * bar reflects the backend coming back up without a page reload — useful when
 * the API restarts during development.
 */
export function useHealth(): UseQueryResult<HealthResponse> {
  return useQuery({
    queryKey: healthQueryKey,
    queryFn: ({ signal }) => apiFetch('/health', healthResponseSchema, { signal }),
    refetchInterval: 30_000,
    staleTime: 10_000,
    // No retry: the 30-second poll *is* the retry. A status indicator exists to
    // report an outage promptly, so silently retrying with backoff before
    // admitting the API is unreachable would defeat its purpose.
    retry: false,
  });
}
