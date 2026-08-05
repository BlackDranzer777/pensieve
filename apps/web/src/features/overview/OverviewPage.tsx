import type { JSX } from 'react';

import { PhasePlaceholder } from '@/components/layout/PhasePlaceholder';

import { PlatformStatusCard } from './PlatformStatusCard';

export function OverviewPage(): JSX.Element {
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <PlatformStatusCard />

      <PhasePlaceholder
        title="Executive overview"
        phase={7}
        willShow={[
          'Total reviews ingested, with valid and rejected record counts',
          'Average rating and sentiment distribution across all brands',
          'Top complaint topic and the fastest-growing topic week over week',
          'Number of languages detected in the current dataset',
          'Active anomalies requiring investigation',
          'Status and duration of the most recent pipeline run',
        ]}
      />
    </div>
  );
}
