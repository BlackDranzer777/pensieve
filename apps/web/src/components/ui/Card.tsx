import type { ReactNode, JSX } from 'react';

import { cn } from '@/lib/utils';

interface CardProps {
  children: ReactNode;
  className?: string;
}

export function Card({ children, className }: CardProps): JSX.Element {
  return (
    <section
      className={cn(
        'bg-surface border border-line rounded-card shadow-card',
        'animate-fade-in',
        className,
      )}
    >
      {children}
    </section>
  );
}

interface CardHeaderProps {
  title: string;
  description?: string;
  /** Rendered on the right of the header — filters, actions, a legend. */
  actions?: ReactNode;
  className?: string;
}

export function CardHeader({
  title,
  description,
  actions,
  className,
}: CardHeaderProps): JSX.Element {
  return (
    <header
      className={cn(
        'flex flex-wrap items-start justify-between gap-3 px-5 py-4 border-b border-line',
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-ink truncate">{title}</h2>
        {description ? <p className="mt-0.5 text-xs text-ink-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2 shrink-0">{actions}</div> : null}
    </header>
  );
}

export function CardBody({ children, className }: CardProps): JSX.Element {
  return <div className={cn('p-5', className)}>{children}</div>;
}
