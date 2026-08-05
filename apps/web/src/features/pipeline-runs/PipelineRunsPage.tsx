import type { JSX } from 'react';

import { PhasePlaceholder } from '@/components/layout/PhasePlaceholder';

export function PipelineRunsPage(): JSX.Element {
  return (
    <PhasePlaceholder
      title="Pipeline runs"
      phase={7}
      willShow={[
        'Run history with status, start and end time, and duration',
        'Records processed, records per second and failed-record counts',
        'Per-stage status timeline from ingestion through to loading',
        'Retry counts and the data-quality score attached to each run',
        'Error details for failed stages, with the diagnostic context preserved',
      ]}
    />
  );
}
