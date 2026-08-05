import type { JSX } from 'react';

import { NavLink } from 'react-router-dom';

import { IconDocument, IconLogo } from '@/components/ui/icons';
import { cn } from '@/lib/utils';
import { routes } from '@/routes/routes';

interface SidebarProps {
  /** Mobile drawer visibility. Ignored at `lg` and above, where it is always shown. */
  open: boolean;
  onNavigate: () => void;
}

export function Sidebar({ open, onNavigate }: SidebarProps): JSX.Element {
  return (
    <>
      {/* Scrim for the mobile drawer. */}
      <div
        className={cn(
          'fixed inset-0 z-30 bg-black/40 lg:hidden transition-opacity',
          open ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={onNavigate}
        aria-hidden="true"
      />

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 w-60 shrink-0 border-r border-line bg-surface',
          'flex flex-col transition-transform duration-200 lg:static',
          // `max-lg:` scopes the off-canvas transform to small screens only.
          // Writing it as `-translate-x-full lg:translate-x-0` would also work,
          // but only because responsive utilities happen to be emitted later in
          // the stylesheet — relying on that ordering is needlessly fragile, and
          // it leaves a transform (and its transition) active at desktop width.
          open ? 'translate-x-0' : 'max-lg:-translate-x-full',
        )}
      >
        <div className="flex h-14 items-center gap-2.5 border-b border-line px-5">
          <IconLogo className="h-6 w-6 text-accent" />
          <div className="leading-tight">
            <p className="text-sm font-semibold tracking-tight text-ink">Pensieve</p>
            <p className="text-2xs text-ink-subtle">Consumer intelligence</p>
          </div>
        </div>

        {/* The label belongs on the <nav> itself: <aside> maps to the
            `complementary` role, so labelling it would not name the landmark
            that assistive technology announces as navigation. */}
        <nav className="flex-1 overflow-y-auto p-3" aria-label="Main navigation">
          <ul className="space-y-0.5">
            {routes.map((route) => (
              <li key={route.path}>
                <NavLink
                  to={route.path}
                  end={route.path === '/'}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      'group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-xs font-medium transition-colors',
                      isActive
                        ? 'bg-accent/10 text-accent'
                        : 'text-ink-muted hover:bg-ink/5 hover:text-ink',
                    )
                  }
                >
                  <route.icon className="h-4 w-4 shrink-0" />
                  <span className="truncate">{route.label}</span>
                  {route.phase ? (
                    <span
                      className="ml-auto rounded bg-ink/5 px-1.5 py-0.5 text-2xs text-ink-subtle"
                      title={`Delivered in build phase ${route.phase}`}
                    >
                      P{route.phase}
                    </span>
                  ) : null}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="border-t border-line p-3">
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 rounded-md px-2.5 py-2 text-xs text-ink-muted transition-colors hover:bg-ink/5 hover:text-ink"
          >
            <IconDocument className="h-4 w-4" />
            API documentation
          </a>
        </div>
      </aside>
    </>
  );
}
