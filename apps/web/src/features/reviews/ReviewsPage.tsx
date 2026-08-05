import type { JSX } from 'react';

import { PhasePlaceholder } from '@/components/layout/PhasePlaceholder';

export function ReviewsPage(): JSX.Element {
  return (
    <PhasePlaceholder
      title="Review explorer"
      phase={7}
      willShow={[
        'Server-side paginated, sortable table of enriched reviews',
        'Full-text search and filters for brand, country, language, topic, sentiment, rating and date',
        'Filter state stored in the URL so any view can be shared or bookmarked',
        'Detail drawer showing original text alongside normalised text',
        'Sentiment confidence and the keywords that produced each topic classification',
        'CSV export of the currently filtered result set',
      ]}
    />
  );
}
