import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query';

import { apiFetch } from '@/lib/api-client';
import { pageSchema, type Page } from '@/types/common';
import {
  reviewDetailSchema,
  reviewFacetsSchema,
  reviewListItemSchema,
  type ReviewDetail,
  type ReviewFacets,
  type ReviewFilters,
  type ReviewListItem,
} from '@/types/reviews';

export function useReviews(filters: ReviewFilters): UseQueryResult<Page<ReviewListItem>> {
  return useQuery({
    queryKey: ['reviews', filters],
    queryFn: ({ signal }) =>
      apiFetch('/reviews', pageSchema(reviewListItemSchema), {
        params: { ...filters },
        signal,
      }),
    // Keep the previous page on screen while the next one loads. Without this
    // the table collapses to a skeleton on every page change, and the whole
    // layout jumps — paging through data becomes unpleasant enough that people
    // stop doing it.
    placeholderData: keepPreviousData,
  });
}

export function useReview(reviewId: string | null): UseQueryResult<ReviewDetail> {
  return useQuery({
    queryKey: ['review', reviewId],
    queryFn: ({ signal }) =>
      apiFetch(`/reviews/${String(reviewId)}`, reviewDetailSchema, { signal }),
    // Only fetch once a row is actually selected.
    enabled: reviewId !== null,
  });
}

export function useReviewFacets(): UseQueryResult<ReviewFacets> {
  return useQuery({
    queryKey: ['reviews', 'facets'],
    queryFn: ({ signal }) => apiFetch('/reviews/facets', reviewFacetsSchema, { signal }),
    // Facets change only when data is reloaded, so an hour is generous but
    // still self-correcting.
    staleTime: 60 * 60 * 1000,
  });
}
