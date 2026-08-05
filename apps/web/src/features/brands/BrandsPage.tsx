import type { JSX } from 'react';

import { PhasePlaceholder } from '@/components/layout/PhasePlaceholder';

export function BrandsPage(): JSX.Element {
  return (
    <PhasePlaceholder
      title="Brand comparison"
      phase={7}
      willShow={[
        'Sentiment split per brand, side by side',
        'Average rating and review volume per brand',
        'Topic distribution showing what each brand is praised or criticised for',
        'Country and language breakdown per brand',
        'Date-range filter applied across every chart on the page',
      ]}
    />
  );
}
