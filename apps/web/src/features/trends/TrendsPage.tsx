import type { JSX } from 'react';

import { PhasePlaceholder } from '@/components/layout/PhasePlaceholder';

export function TrendsPage(): JSX.Element {
  return (
    <PhasePlaceholder
      title="Trends and anomalies"
      phase={7}
      willShow={[
        'Sentiment over time, per brand',
        'Topic trends showing which complaints are growing',
        'Review-volume trend with rolling baseline',
        'Anomaly cards with current value, baseline and percentage change',
        'Severity filter and a deterministic explanation for each anomaly',
      ]}
    />
  );
}
