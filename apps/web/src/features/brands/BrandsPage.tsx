import { useState, type JSX } from 'react';

import { CategoryBarChart } from '@/components/charts/CategoryBarChart';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { DateRangeFilter } from '@/components/ui/Controls';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { useBrandComparison, useCountries } from '@/hooks/useAnalytics';
import { formatCount, formatPercent } from '@/lib/utils';

export function BrandsPage(): JSX.Element {
  const [range, setRange] = useState({ from: '', to: '' });
  const window = { date_from: range.from || undefined, date_to: range.to || undefined };

  const comparison = useBrandComparison(window);
  const countries = useCountries(window);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <Card>
        <CardHeader
          title="Brand comparison"
          description={
            comparison.data
              ? `${formatCount(comparison.data.total_reviews)} reviews in the selected range`
              : 'Sentiment, rating and volume side by side'
          }
          actions={<DateRangeFilter from={range.from} to={range.to} onChange={setRange} />}
        />
        <CardBody className="p-0">
          {comparison.isError ? (
            <ErrorState error={comparison.error} onRetry={() => void comparison.refetch()} />
          ) : comparison.isPending ? (
            <Skeleton className="m-5 h-48" />
          ) : comparison.data.brands.length === 0 ? (
            <EmptyState
              title="No brands in this range"
              description="Widen the date range, or load data with the pipeline."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-subtle">
                    <th className="px-5 py-2 font-medium">Brand</th>
                    <th className="px-3 py-2 text-right font-medium">Reviews</th>
                    <th className="px-3 py-2 text-right font-medium">Avg rating</th>
                    <th className="px-3 py-2 text-right font-medium">Positive</th>
                    <th className="px-3 py-2 text-right font-medium">Negative</th>
                    <th className="px-5 py-2 font-medium">Mix</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {comparison.data.brands.map((brand) => {
                    const total =
                      brand.positive_count + brand.neutral_count + brand.negative_count || 1;
                    return (
                      <tr key={brand.brand_id}>
                        <td className="px-5 py-2.5 font-medium text-ink">{brand.brand}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">
                          {formatCount(brand.review_count)}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">
                          {brand.average_rating != null ? brand.average_rating.toFixed(2) : '—'}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-positive">
                          {brand.positive_percentage != null
                            ? formatPercent(brand.positive_percentage)
                            : '—'}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-negative">
                          {brand.negative_percentage != null
                            ? formatPercent(brand.negative_percentage)
                            : '—'}
                        </td>
                        <td className="px-5 py-2.5">
                          {/* A stacked bar rather than three numbers: the shape
                              of the mix is the comparison people actually make. */}
                          <div
                            className="flex h-2 w-32 overflow-hidden rounded-full bg-ink/5"
                            role="img"
                            aria-label={`${String(brand.positive_count)} positive, ${String(brand.neutral_count)} neutral, ${String(brand.negative_count)} negative`}
                          >
                            <div
                              className="bg-positive"
                              style={{ width: `${String((brand.positive_count / total) * 100)}%` }}
                            />
                            <div
                              className="bg-ink/20"
                              style={{ width: `${String((brand.neutral_count / total) * 100)}%` }}
                            />
                            <div
                              className="bg-negative"
                              style={{ width: `${String((brand.negative_count / total) * 100)}%` }}
                            />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title="Volume by brand" />
          <CardBody>
            {comparison.isPending ? (
              <Skeleton className="h-56 w-full" />
            ) : (
              <CategoryBarChart
                data={(comparison.data?.brands ?? []).map((brand) => ({
                  label: brand.brand,
                  value: brand.review_count,
                }))}
                valueFormatter={formatCount}
              />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="By country" description="Where the reviews come from" />
          <CardBody>
            {countries.isError ? (
              <ErrorState error={countries.error} onRetry={() => void countries.refetch()} />
            ) : countries.isPending ? (
              <Skeleton className="h-56 w-full" />
            ) : (
              <CategoryBarChart
                data={countries.data.map((country) => ({
                  label: country.country,
                  value: country.review_count,
                }))}
                valueFormatter={formatCount}
              />
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
