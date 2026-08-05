import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from '@/app/App';
import { AppProviders } from '@/app/providers';

import './index.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root element #root was not found in index.html.');
}

createRoot(container).render(
  <StrictMode>
    <AppProviders>
      {/* Opt in to the v7 behaviours now: they are the defaults in the next
          major, and adopting them early keeps the upgrade path clear (and the
          console free of future-flag warnings). */}
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <App />
      </BrowserRouter>
    </AppProviders>
  </StrictMode>,
);
