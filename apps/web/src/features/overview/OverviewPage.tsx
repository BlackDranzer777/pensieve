import type { JSX } from 'react';
import { Link } from 'react-router-dom';

import { CategoryBarChart } from '@/components/charts/CategoryBarChart';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { SeverityBadge } from '@/components/ui/Controls';
import { MetricGrid, MetricTile } from '@/components/ui/MetricTile';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { useOverview } from '@/hooks/useAnalytics';
import { formatCount, formatPercent } from '@/lib/utils';

import { PlatformStatusCard } from './PlatformStatusCard';

export function OverviewPage(): JSX.Element {
  const { data, isPending, isError, error, refetch } = useOverview();

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PlatformStatusCard />

      {isError ? (
        <Card>
          <ErrorState error={error} onRetry={() => void refetch()} />
        </Card>
      ) : null}

      <Card>
        <CardHeader
          title="Executive overview"
          description={
            data?.kpis.earliest_review != null
              ? `${data.kpis.earliest_review} to ${data.kpis.latest_review ?? '—'}`
              : 'Every figure is measured from the loaded dataset.'
          }
        />
        <MetricGrid>
          <MetricTile
            label="Reviews"
            value={data ? formatCount(data.kpis.total_reviews) : null}
            loading={isPending}
            hint={
              data
                ? `${formatCount(data.kpis.non_duplicate_reviews)} counted in aggregates`
                : undefined
            }
          />
          <MetricTile
            label="Average rating"
            value={data?.kpis.average_rating != null ? data.kpis.average_rating.toFixed(2) : null}
            loading={isPending}
            hint="out of 5"
          />
          <MetricTile
            label="Negative"
            value={
              data?.kpis.negative_percentage != null
                ? formatPercent(data.kpis.negative_percentage)
                : null
            }
            loading={isPending}
            hint={
              data?.kpis.positive_percentage != null
                ? `${formatPercent(data.kpis.positive_percentage)} positive`
                : undefined
            }
          />
          <MetricTile
            label="Brands"
            value={data ? String(data.kpis.brands) : null}
            loading={isPending}
            hint={data ? `${String(data.kpis.countries)} countries` : undefined}
          />
          <MetricTile
            label="Languages"
            value={data ? String(data.kpis.languages) : null}
            loading={isPending}
            hint="detected, not declared"
          />
        </MetricGrid>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title="Top topics" description="Share of reviews mentioning each topic" />
          <CardBody>
            {isPending ? (
              <Skeleton className="h-56 w-full" />
            ) : (
              <CategoryBarChart
                data={(data?.top_topics ?? []).map((topic) => ({
                  label: topic.topic,
                  value: topic.review_count,
                }))}
                height={220}
                valueFormatter={formatCount}
              />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Languages" description="Detected by Lingua, with confidence" />
          <CardBody className="p-0">
            {isPending ? (
              <Skeleton className="m-5 h-48" />
            ) : (data?.languages.length ?? 0) === 0 ? (
              <EmptyState title="No language data" />
            ) : (
              <ul className="divide-y divide-line">
                {data?.languages.map((language) => (
                  <li
                    key={language.language}
                    className="flex items-center justify-between gap-3 px-5 py-2"
                  >
                    <span className="font-mono text-xs text-ink">{language.language}</span>
                    <div className="flex items-center gap-3">
                      <span className="text-2xs text-ink-subtle">
                        {language.average_confidence != null
                          ? `conf ${language.average_confidence.toFixed(2)}`
                          : '—'}
                      </span>
                      <span className="tabular-nums text-xs text-ink-muted">
                        {formatCount(language.review_count)}
                      </span>
                      <span className="w-12 text-right tabular-nums text-xs font-medium text-ink">
                        {formatPercent(language.percentage)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Active anomalies"
          description="Strongest statistical deviations, each explaining itself"
          actions={
            <Link to="/trends" className="text-2xs font-medium text-accent hover:underline">
              See all
            </Link>
          }
        />
        <CardBody className="p-0">
          {isPending ? (
            <Skeleton className="m-5 h-32" />
          ) : (data?.active_anomalies.length ?? 0) === 0 ? (
            <EmptyState
              title="No anomalies detected"
              description="Nothing in this window cleared the volume, z-score and percentage-change gates."
            />
          ) : (
            <ul className="divide-y divide-line">
              {data?.active_anomalies.map((anomaly) => (
                <li key={anomaly.id} className="flex gap-3 px-5 py-3">
                  <SeverityBadge severity={anomaly.severity} />
                  <div className="min-w-0">
                    <p className="text-xs text-ink">{anomaly.explanation ?? anomaly.metric}</p>
                    <p className="mt-0.5 text-2xs text-ink-subtle">
                      {anomaly.detected_date}
                      {anomaly.topic !== null ? ` · ${anomaly.topic}` : ''}
                      {anomaly.z_score != null ? ` · z = ${anomaly.z_score.toFixed(2)}` : ''}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
