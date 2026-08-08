import type { JSX, ReactNode } from 'react';

import { Skeleton } from '@/components/ui/States';
import { cn } from '@/lib/utils';

interface MetricTileProps {
  label: string;
  /** Already formatted. `null` renders an em dash rather than "0" or "null". */
  value: string | null;
  hint?: ReactNode;
  loading?: boolean;
  className?: string;
}

/**
 * A single headline number.
 *
 * `value` is a pre-formatted string, and `null` means "not available" — which
 * is rendered as a dash. That distinction matters: the API returns `null` for a
 * percentage with no denominator, and showing `0%` there would state something
 * the data does not support.
 */
export function MetricTile({
  label,
  value,
  hint,
  loading = false,
  className,
}: MetricTileProps): JSX.Element {
  return (
    <div className={cn('px-5 py-4', className)}>
      <p className="text-2xs font-medium uppercase tracking-wide text-ink-subtle">{label}</p>
      {loading ? (
        <Skeleton className="mt-2 h-7 w-24" />
      ) : (
        <p className="mt-1 text-metric font-semibold tabular-nums text-ink">
          {value ?? <span className="text-ink-subtle">—</span>}
        </p>
      )}
      {hint ? <div className="mt-0.5 text-xs text-ink-muted">{hint}</div> : null}
    </div>
  );
}

interface MetricGridProps {
  children: ReactNode;
  className?: string;
}

/** Tiles separated by hairlines rather than gaps, so they read as one unit. */
export function MetricGrid({ children, className }: MetricGridProps): JSX.Element {
  return (
    <div
      className={cn(
        'grid grid-cols-2 divide-x divide-y divide-line md:grid-cols-3 lg:grid-cols-5',
        '[&>*]:border-line',
        className,
      )}
    >
      {children}
    </div>
  );
}
