import type { JSX } from 'react';

import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '@/components/layout/AppShell';
import { BrandsPage } from '@/features/brands/BrandsPage';
import { DataQualityPage } from '@/features/data-quality/DataQualityPage';
import { OverviewPage } from '@/features/overview/OverviewPage';
import { PipelineRunsPage } from '@/features/pipeline-runs/PipelineRunsPage';
import { ReviewsPage } from '@/features/reviews/ReviewsPage';
import { TrendsPage } from '@/features/trends/TrendsPage';

export function App(): JSX.Element {
  return (
    <>
      {/* Keyboard users reach the content without tabbing the whole sidebar. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-xs focus:font-medium focus:text-ink focus:shadow-raised"
      >
        Skip to content
      </a>

      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/brands" element={<BrandsPage />} />
          <Route path="/trends" element={<TrendsPage />} />
          <Route path="/reviews" element={<ReviewsPage />} />
          <Route path="/data-quality" element={<DataQualityPage />} />
          <Route path="/pipeline-runs" element={<PipelineRunsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </>
  );
}
