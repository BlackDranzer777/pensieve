import type { JSX } from 'react';

import { StatusDot, type BadgeTone } from '@/components/ui/Badge';
import { IconMenu, IconMoon, IconSun } from '@/components/ui/icons';
import { useHealth } from '@/hooks/useHealth';
import { useTheme } from '@/hooks/useTheme';

interface TopBarProps {
  title: string;
  description: string;
  onOpenMenu: () => void;
}

export function TopBar({ title, description, onOpenMenu }: TopBarProps): JSX.Element {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur sm:px-6">
      <button
        type="button"
        onClick={onOpenMenu}
        className="-ml-1 rounded-md p-2 text-ink-muted hover:bg-ink/5 hover:text-ink lg:hidden"
        aria-label="Open navigation menu"
      >
        <IconMenu className="h-5 w-5" />
      </button>

      <div className="min-w-0 flex-1">
        <h1 className="truncate text-sm font-semibold text-ink">{title}</h1>
        <p className="hidden truncate text-2xs text-ink-muted sm:block">{description}</p>
      </div>

      <ApiStatus />

      <button
        type="button"
        onClick={toggleTheme}
        className="rounded-md p-2 text-ink-muted transition-colors hover:bg-ink/5 hover:text-ink"
        aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      >
        {theme === 'dark' ? (
          <IconSun className="h-4.5 w-4.5" />
        ) : (
          <IconMoon className="h-4.5 w-4.5" />
        )}
      </button>
    </header>
  );
}

/** Live backend status, derived from the health endpoint — never hardcoded. */
function ApiStatus(): JSX.Element {
  const { data, isPending, isError } = useHealth();

  const { tone, label }: { tone: BadgeTone; label: string } = isPending
    ? { tone: 'neutral', label: 'Checking…' }
    : isError
      ? { tone: 'negative', label: 'API unreachable' }
      : // Neither pending nor errored, so `data` is defined here — TypeScript
        // narrows the destructured query result through its discriminants.
        data.status === 'ok'
        ? { tone: 'positive', label: 'All systems normal' }
        : { tone: 'caution', label: 'Degraded' };

  const unavailable =
    data?.checks.filter((check) => check.status !== 'ok').map((c) => c.name) ?? [];

  return (
    <div
      className="hidden items-center gap-2 rounded-full border border-line bg-surface px-2.5 py-1 sm:flex"
      title={unavailable.length > 0 ? `Unavailable: ${unavailable.join(', ')}` : label}
    >
      <StatusDot tone={tone} pulse={tone === 'positive'} />
      <span className="text-2xs font-medium text-ink-muted">{label}</span>
    </div>
  );
}
