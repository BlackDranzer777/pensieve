import { z } from 'zod';

/**
 * Mirrors `HealthResponse` in apps/api/app/schemas/common.py.
 *
 * Kept in `types/` per-domain rather than one giant schema file so each feature
 * imports only what it uses.
 */
export const healthCheckSchema = z.object({
  name: z.string(),
  status: z.enum(['ok', 'unavailable']),
  detail: z.string().nullable().optional(),
});

export const healthResponseSchema = z.object({
  status: z.enum(['ok', 'degraded']),
  version: z.string(),
  environment: z.string(),
  processing_version: z.string(),
  timestamp: z.string(),
  checks: z.array(healthCheckSchema),
});

export type HealthCheck = z.infer<typeof healthCheckSchema>;
export type HealthResponse = z.infer<typeof healthResponseSchema>;
