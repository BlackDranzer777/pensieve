import type { ReactNode, JSX } from 'react';

import { IconAlert, IconList } from '@/components/ui/icons';
import { ApiError } from '@/lib/api-error';
import { cn } from '@/lib/utils';

/**
 * The three states every data-backed view must handle.
 *
 * Centralising them means a new page cannot accidentally ship without a
 * loading or error state — the shape of the component forces the question.
 */

interface SkeletonProps {
  className?: string;
}

/** Shimmering placeholder sized by the caller. */
export function Skeleton({ className }: SkeletonProps): JSX.Element {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={cn('relative overflow-hidden rounded bg-ink/5', className)}
    >
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-ink/5 to-transparent" />
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  title,
  description,
  action,
  className,
}: EmptyStateProps): JSX.Element {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 px-6 py-12 text-center',
        className,
      )}
    >
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-ink/5">
        <IconList className="h-4.5 w-4.5 text-ink-subtle" />
      </div>
      <p className="text-sm font-medium text-ink">{title}</p>
      {description ? <p className="max-w-sm text-xs text-ink-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}

/** Turn any thrown value into something a human can act on. */
export function ErrorState({ error, onRetry, className }: ErrorStateProps): JSX.Element {
  const message =
    error instanceof ApiError
      ? error.userMessage
      : error instanceof Error
        ? error.message
        : 'An unknown error occurred.';

  const code = error instanceof ApiError ? error.code : undefined;

  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center gap-2 px-6 py-12 text-center',
        className,
      )}
    >
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-negative/10">
        <IconAlert className="h-5 w-5 text-negative" />
      </div>
      <p className="text-sm font-medium text-ink">Something went wrong</p>
      <p className="max-w-md text-xs text-ink-muted">{message}</p>
      {code ? <code className="text-2xs text-ink-subtle font-mono">{code}</code> : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink hover:bg-ink/5 transition-colors"
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}
