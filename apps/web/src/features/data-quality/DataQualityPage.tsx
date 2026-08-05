import type { JSX } from 'react';

import { PhasePlaceholder } from '@/components/layout/PhasePlaceholder';

export function DataQualityPage(): JSX.Element {
  return (
    <PhasePlaceholder
      title="Data quality"
      phase={7}
      willShow={[
        'Overall quality score with the weighted formula that produced it',
        'Valid, rejected, duplicate and missing-value counts per batch',
        'Schema failures broken down by rule and by field',
        'Quarantine reasons, ranked by frequency',
        'Quality score over time, so regressions are visible',
      ]}
    />
  );
}
