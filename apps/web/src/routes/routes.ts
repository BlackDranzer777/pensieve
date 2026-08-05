import type { ComponentType } from 'react';

import {
  IconBrands,
  IconOverview,
  IconPipeline,
  IconQuality,
  IconReviews,
  IconTrends,
  type IconProps,
} from '@/components/ui/icons';

/**
 * Route definitions live in one place so the sidebar, the router and the page
 * titles cannot drift apart.
 *
 * `phase` records which build phase delivers the page. It drives an honest
 * "not built yet" state instead of a broken-looking empty page, and each entry
 * loses the field as its page ships.
 */
export interface RouteDefinition {
  path: string;
  label: string;
  description: string;
  icon: ComponentType<IconProps>;
  /** Build phase that delivers this page; `undefined` means it is live. */
  phase?: number;
}

export const routes: readonly RouteDefinition[] = [
  {
    path: '/',
    label: 'Overview',
    description: 'Executive summary of volume, sentiment, topics and platform health',
    icon: IconOverview,
    phase: 7,
  },
  {
    path: '/brands',
    label: 'Brands',
    description: 'Compare sentiment, rating and topic mix across brands',
    icon: IconBrands,
    phase: 7,
  },
  {
    path: '/trends',
    label: 'Trends & anomalies',
    description: 'Sentiment and topic movement over time, with detected anomalies',
    icon: IconTrends,
    phase: 7,
  },
  {
    path: '/reviews',
    label: 'Review explorer',
    description: 'Search, filter and inspect individual enriched reviews',
    icon: IconReviews,
    phase: 7,
  },
  {
    path: '/data-quality',
    label: 'Data quality',
    description: 'Quality score, rejected records and quarantine reasons',
    icon: IconQuality,
    phase: 7,
  },
  {
    path: '/pipeline-runs',
    label: 'Pipeline runs',
    description: 'Run history, stage timings, throughput and failures',
    icon: IconPipeline,
    phase: 7,
  },
] as const;
