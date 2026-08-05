import { useEffect, useState, type JSX } from 'react';
import { Outlet, useLocation } from 'react-router-dom';

import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { routes } from '@/routes/routes';

export function AppShell(): JSX.Element {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  const active = routes.find((route) =>
    route.path === '/' ? location.pathname === '/' : location.pathname.startsWith(route.path),
  );

  // Keep the document title in sync so browser history and tabs are useful.
  useEffect(() => {
    document.title = active ? `${active.label} · Pensieve` : 'Pensieve';
  }, [active]);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen bg-canvas">
      <Sidebar
        open={menuOpen}
        onNavigate={() => {
          setMenuOpen(false);
        }}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          title={active?.label ?? 'Pensieve'}
          description={active?.description ?? ''}
          onOpenMenu={() => {
            setMenuOpen(true);
          }}
        />

        {/* `id="main"` is the skip-link target in App.tsx. */}
        <main id="main" tabIndex={-1} className="flex-1 px-4 py-5 sm:px-6 sm:py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
