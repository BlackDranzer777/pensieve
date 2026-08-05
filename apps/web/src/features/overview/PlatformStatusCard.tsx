import type { JSX } from 'react';

import { useHealth } from '@/hooks/useHealth';
import { Badge, StatusDot, type BadgeTone } from '@/components/ui/Badge';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { ErrorState, Skeleton } from '@/components/ui/States';

/**
 * Live platform status, read from `GET /api/v1/health`.
 *
 * This is the first real end-to-end slice: React -> TanStack Query -> Zod ->
 * FastAPI -> PostgreSQL. Every value here comes from the API; nothing is
 * hardcoded.
 */
export function PlatformStatusCard(): JSX.Element {
  const { data, isPending, isError, error, refetch, dataUpdatedAt } = useHealth();

  return (
    <Card>
      <CardHeader
        title="Platform status"
        description="Live health of the API and its dependencies"
        actions={
          data ? (
            <Badge tone={data.status === 'ok' ? 'positive' : 'caution'}>
              {data.status === 'ok' ? 'Healthy' : 'Degraded'}
            </Badge>
          ) : null
        }
      />
      <CardBody>
        {isPending ? (
          <div className="space-y-2.5">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-4 w-32" />
          </div>
        ) : isError ? (
          <ErrorState error={error} onRetry={() => void refetch()} className="py-6" />
        ) : (
          <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
              <Field label="API version" value={data.version} mono />
              <Field label="Environment" value={data.environment} />
              <Field label="Processing version" value={data.processing_version} mono />
            </dl>

            <div>
              <p className="text-2xs font-semibold uppercase tracking-wide text-ink-subtle">
                Dependencies
              </p>
              <ul className="mt-2 divide-y divide-line rounded-md border border-line">
                {data.checks.map((check) => {
                  const tone: BadgeTone = check.status === 'ok' ? 'positive' : 'negative';
                  return (
                    <li key={check.name} className="flex items-center gap-2.5 px-3 py-2">
                      <StatusDot tone={tone} />
                      <span className="text-xs font-medium capitalize text-ink">{check.name}</span>
                      <span className="ml-auto text-2xs text-ink-muted">
                        {check.status === 'ok' ? 'connected' : 'unavailable'}
                      </span>
                    </li>
                  );
                })}
              </ul>

              {data.checks.some((check) => check.status !== 'ok') ? (
                <p className="mt-2 text-2xs text-ink-muted">
                  Start the database with{' '}
                  <code className="font-mono text-ink">docker compose up postgres</code>, then this
                  panel updates on its own.
                </p>
              ) : null}
            </div>

            <p className="text-2xs text-ink-subtle">
              Last checked {new Date(dataUpdatedAt).toLocaleTimeString()}
            </p>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}): JSX.Element {
  return (
    <div className="min-w-0">
      <dt className="text-2xs uppercase tracking-wide text-ink-subtle">{label}</dt>
      <dd className={`mt-0.5 truncate text-xs text-ink ${mono ? 'font-mono' : ''}`}>{value}</dd>
    </div>
  );
}
