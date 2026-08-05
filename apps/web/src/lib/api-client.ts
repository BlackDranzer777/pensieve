import type { z } from 'zod';

import { ApiError, apiErrorBodySchema } from './api-error';

/**
 * Base URL for the API.
 *
 * Empty by default so requests go to `/api/...` on the current origin, which
 * the Vite dev server proxies to the backend and nginx serves directly in
 * production. Set `VITE_API_BASE_URL` to point at a different host.
 */
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export const API_PREFIX = '/api/v1';

export type QueryParams = Record<
  string,
  string | number | boolean | null | undefined | Array<string | number>
>;

/** Build a query string, dropping empty values and expanding arrays. */
export function buildQuery(params: QueryParams | undefined): string {
  if (!params) return '';
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, String(item));
    } else {
      search.append(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

async function parseErrorResponse(response: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return new ApiError({
      kind: 'http',
      status: response.status,
      message: `Request failed with status ${response.status}.`,
    });
  }

  const parsed = apiErrorBodySchema.safeParse(body);
  if (parsed.success) {
    return new ApiError({
      kind: 'http',
      status: response.status,
      code: parsed.data.error.code,
      message: parsed.data.error.message,
      details: parsed.data.error.details,
    });
  }
  return new ApiError({
    kind: 'http',
    status: response.status,
    message: `Request failed with status ${response.status}.`,
  });
}

/**
 * Fetch JSON from the API and validate it against a Zod schema.
 *
 * Validating on the client is not ceremony: the backend and frontend evolve in
 * separate languages, and a parse failure here turns a silent rendering bug
 * into an explicit, debuggable error naming the offending field.
 */
export async function apiFetch<TOut>(
  path: string,
  schema: z.ZodType<TOut>,
  options: { params?: QueryParams; signal?: AbortSignal; init?: RequestInit } = {},
): Promise<TOut> {
  const url = `${BASE_URL}${API_PREFIX}${path}${buildQuery(options.params)}`;

  // Built via the Headers constructor rather than object spread: `HeadersInit`
  // may be an array or a Headers instance, both of which spread incorrectly.
  const headers = new Headers(options.init?.headers);
  headers.set('Accept', 'application/json');

  let response: Response;
  try {
    response = await fetch(url, {
      ...options.init,
      signal: options.signal ?? null,
      headers,
    });
  } catch (cause) {
    // An aborted request is a normal part of React Query's lifecycle, not a
    // failure worth surfacing — re-throw it untouched so callers can ignore it.
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError({
      kind: 'network',
      message: 'Network request failed.',
      cause,
    });
  }

  if (!response.ok) throw await parseErrorResponse(response);

  const raw: unknown = await response.json();
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    const where = issue ? `${issue.path.join('.') || '<root>'}: ${issue.message}` : 'unknown field';
    throw new ApiError({
      kind: 'schema',
      status: response.status,
      message: `Unexpected response shape from ${path} (${where}).`,
      details: { issues: parsed.error.issues },
      cause: parsed.error,
    });
  }
  return parsed.data;
}
