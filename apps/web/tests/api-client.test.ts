import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import { apiFetch, buildQuery } from '@/lib/api-client';
import { ApiError } from '@/lib/api-error';

import { mockFetchJson, mockFetchNetworkError } from './test-utils';

const schema = z.object({ value: z.number() });

describe('buildQuery', () => {
  it('drops empty values so the URL stays clean', () => {
    expect(buildQuery({ a: 1, b: undefined, c: null, d: '' })).toBe('?a=1');
  });

  it('expands arrays into repeated keys', () => {
    expect(buildQuery({ topic: ['price', 'delivery'] })).toBe('?topic=price&topic=delivery');
  });

  it('returns an empty string when there is nothing to encode', () => {
    expect(buildQuery(undefined)).toBe('');
    expect(buildQuery({})).toBe('');
  });
});

describe('apiFetch', () => {
  it('returns parsed data on success', async () => {
    mockFetchJson({ value: 42 });
    await expect(apiFetch('/thing', schema)).resolves.toEqual({ value: 42 });
  });

  it('requests the versioned path', async () => {
    const mock = mockFetchJson({ value: 1 });
    await apiFetch('/thing', schema, { params: { page: 2 } });
    expect(mock.mock.calls[0]?.[0]).toContain('/api/v1/thing?page=2');
  });

  it('surfaces the API error envelope', async () => {
    mockFetchJson(
      { error: { code: 'not_found', message: 'Review abc was not found.' } },
      { status: 404 },
    );

    const error = await apiFetch('/thing', schema).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).kind).toBe('http');
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).code).toBe('not_found');
    expect((error as ApiError).message).toBe('Review abc was not found.');
  });

  it('rejects a 200 response whose shape does not match, naming the bad field', async () => {
    // The important case: without schema validation this would flow into the UI
    // and render as `undefined` somewhere far from the cause.
    mockFetchJson({ value: 'not-a-number' });

    const error = await apiFetch('/thing', schema).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).kind).toBe('schema');
    expect((error as ApiError).message).toContain('value');
  });

  it('reports a network failure distinctly from an HTTP error', async () => {
    mockFetchNetworkError();

    const error = await apiFetch('/thing', schema).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).kind).toBe('network');
    expect((error as ApiError).userMessage).toContain('Could not reach');
  });
});
