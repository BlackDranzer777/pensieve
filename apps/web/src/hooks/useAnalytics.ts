import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { z } from 'zod';

import { apiFetch, type QueryParams } from '@/lib/api-client';
import {
  anomalySchema,
  brandComparisonSchema,
  brandSummarySchema,
  countryPointSchema,
  languagePointSchema,
  overviewSchema,
  sentimentTrendsSchema,
  topicTrendsSchema,
  type Anomaly,
  type BrandComparison,
  type BrandSummary,
  type CountryPoint,
  type LanguagePoint,
  type Overview,
  type SentimentTrends,
  type TopicTrends,
} from '@/types/analytics';
import { pageSchema, type Page } from '@/types/common';

/**
 * Analytics queries.
 *
 * Every hook takes the date window as part of its query key, so changing the
 * range refetches instead of showing the previous window's numbers under a new
 * label — a stale chart with a fresh title is worse than a spinner.
 */

export interface DateWindow {
  date_from?: string;
  date_to?: string;
}

/** Aggregate data changes only when the loader runs, so cache it generously. */
const AGGREGATE_STALE_MS = 60_000;

function windowParams(window: DateWindow): QueryParams {
  return { date_from: window.date_from, date_to: window.date_to };
}

export function useOverview(window: DateWindow = {}): UseQueryResult<Overview> {
  return useQuery({
    queryKey: ['overview', window],
    queryFn: ({ signal }) =>
      apiFetch('/overview', overviewSchema, { params: windowParams(window), signal }),
    staleTime: AGGREGATE_STALE_MS,
  });
}

export function useBrands(window: DateWindow = {}): UseQueryResult<BrandSummary[]> {
  return useQuery({
    queryKey: ['brands', window],
    queryFn: ({ signal }) =>
      apiFetch('/brands', z.array(brandSummarySchema), {
        params: windowParams(window),
        signal,
      }),
    staleTime: AGGREGATE_STALE_MS,
  });
}

export function useBrandComparison(window: DateWindow = {}): UseQueryResult<BrandComparison> {
  return useQuery({
    queryKey: ['brands', 'comparison', window],
    queryFn: ({ signal }) =>
      apiFetch('/brands/comparison', brandComparisonSchema, {
        params: windowParams(window),
        signal,
      }),
    staleTime: AGGREGATE_STALE_MS,
  });
}

export function useCountries(window: DateWindow = {}): UseQueryResult<CountryPoint[]> {
  return useQuery({
    queryKey: ['countries', window],
    queryFn: ({ signal }) =>
      apiFetch('/countries', z.array(countryPointSchema), {
        params: windowParams(window),
        signal,
      }),
    staleTime: AGGREGATE_STALE_MS,
  });
}

export function useLanguages(window: DateWindow = {}): UseQueryResult<LanguagePoint[]> {
  return useQuery({
    queryKey: ['languages', window],
    queryFn: ({ signal }) =>
      apiFetch('/languages', z.array(languagePointSchema), {
        params: windowParams(window),
        signal,
      }),
    staleTime: AGGREGATE_STALE_MS,
  });
}

export function useSentimentTrends(window: DateWindow = {}): UseQueryResult<SentimentTrends> {
  return useQuery({
    queryKey: ['trends', 'sentiment', window],
    queryFn: ({ signal }) =>
      apiFetch('/trends/sentiment', sentimentTrendsSchema, {
        params: windowParams(window),
        signal,
      }),
    staleTime: AGGREGATE_STALE_MS,
  });
}

export function useTopicTrends(window: DateWindow = {}): UseQueryResult<TopicTrends> {
  return useQuery({
    queryKey: ['trends', 'topics', window],
    queryFn: ({ signal }) =>
      apiFetch('/trends/topics', topicTrendsSchema, {
        params: windowParams(window),
        signal,
      }),
    staleTime: AGGREGATE_STALE_MS,
  });
}

export interface AnomalyQuery extends DateWindow {
  severity?: string[];
  metric?: string;
  page?: number;
  page_size?: number;
}

export function useAnomalies(query: AnomalyQuery = {}): UseQueryResult<Page<Anomaly>> {
  return useQuery({
    queryKey: ['anomalies', query],
    queryFn: ({ signal }) =>
      apiFetch('/anomalies', pageSchema(anomalySchema), {
        params: {
          date_from: query.date_from,
          date_to: query.date_to,
          severity: query.severity,
          metric: query.metric,
          page: query.page,
          page_size: query.page_size,
        },
        signal,
      }),
    staleTime: AGGREGATE_STALE_MS,
  });
}
