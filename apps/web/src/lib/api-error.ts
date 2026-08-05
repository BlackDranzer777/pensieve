import { z } from 'zod';

/** The error envelope every Pensieve endpoint returns (see api/app/core/errors.py). */
export const apiErrorBodySchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.string(), z.unknown()).optional(),
  }),
});

export type ApiErrorBody = z.infer<typeof apiErrorBodySchema>;

/**
 * A failed API call. Distinguishes the three failure modes the UI must treat
 * differently:
 *
 *  - `network`  — the request never reached the server (offline, API down)
 *  - `http`     — the server answered with an error envelope
 *  - `schema`   — the server answered 200 with a body we could not parse
 *
 * The third case matters more than it looks: silently accepting an unexpected
 * shape is how dashboards end up rendering `undefined` as a metric.
 */
export class ApiError extends Error {
  readonly kind: 'network' | 'http' | 'schema';
  readonly status: number | undefined;
  readonly code: string;
  readonly details: Record<string, unknown> | undefined;

  constructor(args: {
    kind: 'network' | 'http' | 'schema';
    message: string;
    status?: number;
    code?: string;
    details?: Record<string, unknown>;
    cause?: unknown;
  }) {
    super(args.message, { cause: args.cause });
    this.name = 'ApiError';
    this.kind = args.kind;
    this.status = args.status;
    this.code = args.code ?? args.kind;
    this.details = args.details;
  }

  /** A message safe and useful to show a user. */
  get userMessage(): string {
    switch (this.kind) {
      case 'network':
        return 'Could not reach the Pensieve API. Check that the backend is running.';
      case 'schema':
        return 'The API returned data in an unexpected format.';
      default:
        return this.message;
    }
  }
}
