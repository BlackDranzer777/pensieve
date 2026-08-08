import { useCallback, useMemo, useState, type JSX } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Badge } from '@/components/ui/Badge';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import {
  ChipFilter,
  DateRangeFilter,
  PaginationBar,
  SearchInput,
  SentimentBadge,
} from '@/components/ui/Controls';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { useReview, useReviewFacets, useReviews } from '@/hooks/useReviews';
import { formatCount } from '@/lib/utils';
import type { ReviewFilters } from '@/types/reviews';

const PAGE_SIZE = 25;

/**
 * Read filters from the URL.
 *
 * The URL is the single source of truth for filter state rather than component
 * state. It costs a little plumbing and buys back-button behaviour, refresh
 * safety, and the ability to paste "the filtered view I am looking at" to a
 * colleague — which is most of the value of a review explorer.
 */
function parseFilters(params: URLSearchParams): ReviewFilters {
  const list = (key: string): string[] | undefined => {
    const values = params.getAll(key);
    return values.length > 0 ? values : undefined;
  };
  const page = Number(params.get('page') ?? '1');
  return {
    q: params.get('q') ?? undefined,
    brand: list('brand'),
    country: list('country'),
    language: list('language'),
    sentiment: list('sentiment'),
    topic: list('topic'),
    date_from: params.get('date_from') ?? undefined,
    date_to: params.get('date_to') ?? undefined,
    include_duplicates: params.get('include_duplicates') === 'true' ? true : undefined,
    page: Number.isFinite(page) && page > 0 ? page : 1,
    page_size: PAGE_SIZE,
  };
}

export function ReviewsPage(): JSX.Element {
  const [params, setParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const filters = useMemo(() => parseFilters(params), [params]);
  const reviews = useReviews(filters);
  const facets = useReviewFacets();
  const detail = useReview(selectedId);

  /** Update one key, always resetting to page 1 — except when paging. */
  const update = useCallback(
    (mutate: (next: URLSearchParams) => void, resetPage = true) => {
      const next = new URLSearchParams(params);
      mutate(next);
      if (resetPage) next.delete('page');
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  const toggle = useCallback(
    (key: string, value: string) => {
      update((next) => {
        const current = next.getAll(key);
        next.delete(key);
        for (const item of current.includes(value)
          ? current.filter((entry) => entry !== value)
          : [...current, value]) {
          next.append(key, item);
        }
      });
    },
    [update],
  );

  const activeFilterCount =
    (filters.brand?.length ?? 0) +
    (filters.country?.length ?? 0) +
    (filters.language?.length ?? 0) +
    (filters.sentiment?.length ?? 0) +
    (filters.topic?.length ?? 0);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <Card>
        <CardHeader
          title="Filters"
          description="Duplicates are hidden by default so this table agrees with the aggregates"
          actions={
            activeFilterCount > 0 ? (
              <button
                type="button"
                onClick={() => setParams(new URLSearchParams(), { replace: true })}
                className="text-2xs font-medium text-accent hover:underline"
              >
                Clear {activeFilterCount} filters
              </button>
            ) : null
          }
        />
        <CardBody className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <SearchInput
              value={filters.q ?? ''}
              onChange={(value) =>
                update((next) => {
                  if (value) next.set('q', value);
                  else next.delete('q');
                })
              }
              placeholder="Search review text or product (3+ characters)…"
              className="min-w-64 flex-1"
            />
            <DateRangeFilter
              from={filters.date_from ?? ''}
              to={filters.date_to ?? ''}
              onChange={({ from, to }) =>
                update((next) => {
                  if (from) next.set('date_from', from);
                  else next.delete('date_from');
                  if (to) next.set('date_to', to);
                  else next.delete('date_to');
                })
              }
            />
            <label className="flex items-center gap-1.5 text-2xs text-ink-muted">
              <input
                type="checkbox"
                checked={filters.include_duplicates === true}
                onChange={(event) =>
                  update((next) => {
                    if (event.target.checked) next.set('include_duplicates', 'true');
                    else next.delete('include_duplicates');
                  })
                }
              />
              Include duplicates
            </label>
          </div>

          {facets.isPending ? (
            <Skeleton className="h-20 w-full" />
          ) : facets.isError ? (
            <ErrorState error={facets.error} onRetry={() => void facets.refetch()} />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <ChipFilter
                label="Brand"
                options={facets.data.brands}
                selected={filters.brand ?? []}
                onToggle={(value) => toggle('brand', value)}
              />
              <ChipFilter
                label="Sentiment"
                options={facets.data.sentiments}
                selected={filters.sentiment ?? []}
                onToggle={(value) => toggle('sentiment', value)}
              />
              <ChipFilter
                label="Language"
                options={facets.data.languages}
                selected={filters.language ?? []}
                onToggle={(value) => toggle('language', value)}
              />
              <ChipFilter
                label="Country"
                options={facets.data.countries}
                selected={filters.country ?? []}
                onToggle={(value) => toggle('country', value)}
              />
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Reviews"
          description={
            reviews.data ? `${formatCount(reviews.data.meta.total_items)} matching` : undefined
          }
        />
        <CardBody className="p-0">
          {reviews.isError ? (
            <ErrorState error={reviews.error} onRetry={() => void reviews.refetch()} />
          ) : reviews.isPending ? (
            <Skeleton className="m-5 h-64" />
          ) : reviews.data.items.length === 0 ? (
            <EmptyState
              title="No reviews match these filters"
              description="Try clearing a filter or widening the date range."
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-subtle">
                      <th className="px-5 py-2 font-medium">Review</th>
                      <th className="px-3 py-2 font-medium">Brand</th>
                      <th className="px-3 py-2 font-medium">Sentiment</th>
                      <th className="px-3 py-2 font-medium">Topic</th>
                      <th className="px-3 py-2 text-right font-medium">Rating</th>
                      <th className="px-5 py-2 font-medium">Date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {reviews.data.items.map((review) => (
                      <tr
                        key={review.id}
                        onClick={() => setSelectedId(review.id)}
                        className="cursor-pointer hover:bg-ink/[0.03]"
                      >
                        <td className="max-w-md px-5 py-2.5">
                          <p className="truncate text-ink">{review.original_text}</p>
                          <p className="text-2xs text-ink-subtle">
                            {review.external_review_id}
                            {review.language !== null ? ` · ${review.language}` : ''}
                            {review.is_duplicate ? ' · duplicate' : ''}
                          </p>
                        </td>
                        <td className="px-3 py-2.5 text-ink-muted">{review.brand}</td>
                        <td className="px-3 py-2.5">
                          <SentimentBadge sentiment={review.sentiment} />
                        </td>
                        <td className="px-3 py-2.5 text-ink-muted">
                          {review.primary_topic ?? '—'}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">
                          {review.rating ?? '—'}
                        </td>
                        <td className="px-5 py-2.5 text-2xs text-ink-subtle">
                          {review.review_created_at.slice(0, 10)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <PaginationBar
                className="border-t border-line"
                page={reviews.data.meta.page}
                totalPages={reviews.data.meta.total_pages}
                totalItems={reviews.data.meta.total_items}
                onPageChange={(page) =>
                  update((next) => {
                    next.set('page', String(page));
                  }, false)
                }
              />
            </>
          )}
        </CardBody>
      </Card>

      {selectedId !== null ? (
        <Card>
          <CardHeader
            title="Review detail"
            description="Including how the pipeline processed it"
            actions={
              <button
                type="button"
                onClick={() => setSelectedId(null)}
                className="text-2xs font-medium text-ink-muted hover:underline"
              >
                Close
              </button>
            }
          />
          <CardBody>
            {detail.isError ? (
              <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
            ) : detail.isPending ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <div className="space-y-3 text-xs">
                <p className="text-ink">{detail.data.original_text}</p>
                <dl className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
                  <Field label="Brand" value={detail.data.brand} />
                  <Field label="Product" value={detail.data.product} />
                  <Field label="Country" value={detail.data.country} />
                  <Field label="Source" value={detail.data.source} />
                  <Field
                    label="Language"
                    value={
                      detail.data.language !== null
                        ? `${detail.data.language} (${detail.data.language_confidence?.toFixed(2) ?? '—'})`
                        : null
                    }
                  />
                  <Field
                    label="Sentiment model"
                    value={detail.data.sentiment_model_version}
                  />
                  <Field label="Words" value={detail.data.word_count?.toString() ?? null} />
                  <Field label="Duplicate of" value={detail.data.is_duplicate_of} />
                </dl>
                <div>
                  <p className="text-2xs font-medium uppercase tracking-wide text-ink-subtle">
                    Topics
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {detail.data.topics.map((topic) => (
                      <Badge key={topic.topic} tone={topic.is_primary ? 'accent' : 'neutral'}>
                        {topic.topic}
                        {topic.is_primary ? ' · primary' : ''}
                      </Badge>
                    ))}
                  </div>
                  {detail.data.topics[0]?.matched_keywords != null ? (
                    <p className="mt-1.5 text-2xs text-ink-subtle">
                      matched: {detail.data.topics[0].matched_keywords}
                    </p>
                  ) : null}
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null }): JSX.Element {
  return (
    <div className="flex gap-2">
      <dt className="w-28 shrink-0 text-ink-subtle">{label}</dt>
      <dd className="min-w-0 truncate text-ink-muted">{value ?? '—'}</dd>
    </div>
  );
}
