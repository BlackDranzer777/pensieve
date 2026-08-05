import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { App } from '@/app/App';

import {
  healthFixture,
  mockFetchJson,
  mockFetchNetworkError,
  renderWithProviders,
} from './test-utils';

describe('application shell', () => {
  it('renders navigation for every dashboard page', () => {
    mockFetchJson(healthFixture());
    renderWithProviders(<App />);

    const nav = screen.getByRole('navigation', { name: /main navigation/i });
    for (const label of [
      'Overview',
      'Brands',
      'Trends & anomalies',
      'Review explorer',
      'Data quality',
      'Pipeline runs',
    ]) {
      expect(within(nav).getByRole('link', { name: new RegExp(label, 'i') })).toBeInTheDocument();
    }
  });

  it('navigates between pages via the sidebar', async () => {
    mockFetchJson(healthFixture());
    const user = userEvent.setup();
    renderWithProviders(<App />);

    await user.click(screen.getByRole('link', { name: /review explorer/i }));

    expect(
      await screen.findByText(/CSV export of the currently filtered result set/i),
    ).toBeInTheDocument();
  });

  it('redirects an unknown route to the overview', async () => {
    mockFetchJson(healthFixture());
    renderWithProviders(<App />, { route: '/nope' });

    expect(await screen.findByRole('heading', { name: /platform status/i })).toBeInTheDocument();
  });

  it('exposes a skip link for keyboard users', () => {
    mockFetchJson(healthFixture());
    renderWithProviders(<App />);

    expect(screen.getByRole('link', { name: /skip to content/i })).toHaveAttribute('href', '#main');
  });
});

describe('platform status card', () => {
  it('shows a loading state before data arrives', () => {
    mockFetchJson(healthFixture());
    renderWithProviders(<App />);

    expect(screen.getAllByRole('status', { name: /loading/i }).length).toBeGreaterThan(0);
  });

  it('renders live values from the health endpoint', async () => {
    mockFetchJson(healthFixture({ version: '9.9.9', processing_version: '3.2.1' }));
    renderWithProviders(<App />);

    expect(await screen.findByText('9.9.9')).toBeInTheDocument();
    expect(screen.getByText('3.2.1')).toBeInTheDocument();
    expect(screen.getByText('connected')).toBeInTheDocument();
  });

  it('reports a degraded database rather than hiding it', async () => {
    mockFetchJson(
      healthFixture({
        status: 'degraded',
        checks: [{ name: 'database', status: 'unavailable', detail: 'OperationalError: refused' }],
      }),
    );
    renderWithProviders(<App />);

    expect(await screen.findByText('unavailable')).toBeInTheDocument();
    expect(screen.getAllByText(/degraded/i).length).toBeGreaterThan(0);
  });

  it('shows an actionable error state when the API is unreachable', async () => {
    mockFetchNetworkError();
    renderWithProviders(<App />);

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText(/could not reach the pensieve api/i)).toBeInTheDocument();
    expect(within(alert).getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('retries when the user asks it to', async () => {
    const failing = mockFetchNetworkError();
    const user = userEvent.setup();
    renderWithProviders(<App />);

    const alert = await screen.findByRole('alert');
    const callsBefore = failing.mock.calls.length;

    mockFetchJson(healthFixture());
    await user.click(within(alert).getByRole('button', { name: /try again/i }));

    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
    expect(callsBefore).toBeGreaterThan(0);
  });
});
