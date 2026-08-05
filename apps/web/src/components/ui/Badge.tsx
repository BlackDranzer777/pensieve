import type { ReactNode, JSX } from 'react';

import { cn } from '@/lib/utils';

export type BadgeTone = 'neutral' | 'accent' | 'positive' | 'caution' | 'negative' | 'info';

const toneClasses: Record<BadgeTone, string> = {
  neutral: 'bg-ink/5 text-ink-muted ring-ink/10',
  accent: 'bg-accent/10 text-accent ring-accent/20',
  positive: 'bg-positive/10 text-positive ring-positive/20',
  caution: 'bg-caution/10 text-caution ring-caution/20',
  negative: 'bg-negative/10 text-negative ring-negative/20',
  info: 'bg-info/10 text-info ring-info/20',
};

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}

export function Badge({ children, tone = 'neutral', className }: BadgeProps): JSX.Element {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5',
        'text-2xs font-medium ring-1 ring-inset whitespace-nowrap',
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

interface StatusDotProps {
  tone: BadgeTone;
  /** Adds a soft pulse — use only for genuinely live state. */
  pulse?: boolean;
  className?: string;
}

const dotClasses: Record<BadgeTone, string> = {
  neutral: 'bg-ink-subtle',
  accent: 'bg-accent',
  positive: 'bg-positive',
  caution: 'bg-caution',
  negative: 'bg-negative',
  info: 'bg-info',
};

export function StatusDot({ tone, pulse = false, className }: StatusDotProps): JSX.Element {
  return (
    <span className={cn('relative inline-flex h-2 w-2 shrink-0', className)}>
      {pulse ? (
        <span
          className={cn(
            'absolute inline-flex h-full w-full rounded-full opacity-60',
            dotClasses[tone],
          )}
          style={{ animation: 'ping 2s cubic-bezier(0,0,0.2,1) infinite' }}
        />
      ) : null}
      <span className={cn('relative inline-flex h-2 w-2 rounded-full', dotClasses[tone])} />
    </span>
  );
}
