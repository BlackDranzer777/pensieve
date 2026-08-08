import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { z } from 'zod';

import { apiFetch } from '@/lib/api-client';
import { pageSchema, type Page } from '@/types/common';
import {
  dataQualityReportSchema,
  pipelineRunDetailSchema,
  pipelineRunSchema,
  qualityTrendPointSchema,
  type DataQualityReport,
  type PipelineRun,
  type PipelineRunDetail,
  type QualityTrendPoint,
} from '@/types/telemetry';

export function usePipelineRuns(page = 1, pageSize = 25): UseQueryResult<Page<PipelineRun>> {
  return useQuery({
    queryKey: ['pipeline-runs', page, pageSize],
    queryFn: ({ signal }) =>
      apiFetch('/pipeline-runs', pageSchema(pipelineRunSchema), {
        params: { page, page_size: pageSize },
        signal,
      }),
  });
}

export function usePipelineRun(runId: string | null): UseQueryResult<PipelineRunDetail> {
  return useQuery({
    queryKey: ['pipeline-run', runId],
    queryFn: ({ signal }) =>
      apiFetch(`/pipeline-runs/${String(runId)}`, pipelineRunDetailSchema, { signal }),
    enabled: runId !== null,
  });
}

export function useDataQuality(runId?: string): UseQueryResult<DataQualityReport> {
  return useQuery({
    queryKey: ['data-quality', runId ?? 'latest'],
    queryFn: ({ signal }) =>
      apiFetch('/data-quality', dataQualityReportSchema, {
        params: { run_id: runId },
        signal,
      }),
  });
}

export function useQualityTrend(limit = 30): UseQueryResult<QualityTrendPoint[]> {
  return useQuery({
    queryKey: ['data-quality', 'trend', limit],
    queryFn: ({ signal }) =>
      apiFetch('/data-quality/trend', z.array(qualityTrendPointSchema), {
        params: { limit },
        signal,
      }),
  });
}
