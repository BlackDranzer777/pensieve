import { useMemo, useState, type JSX } from 'react';

import { TimeSeriesChart, type SeriesSpec } from '@/components/charts/TimeSeriesChart';
import { seriesColor, token } from '@/components/charts/chart-theme';
import { Badge } from '@/components/ui/Badge';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import {
  ChipFilter,
  DateRangeFilter,
  SelectFilter,
  SeverityBadge,
} from '@/components/ui/Controls';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { useAnomalies, useBrands, useSentimentTrends, useTopicTrends } from '@/hooks/useAnalytics';
import { formatCount, formatPercent } from '@/lib/utils';

const SEVERITIES = ['low', 'medium', 'high', 'critical'] as const;

/** How many topics to plot. Eleven lines is unreadable; five is a chart. */
const TOPIC_LINE_LIMIT = 5;

export function TrendsPage(): JSX.Element {
  const [range, setRange] = useState({ from: '', to: '' });
  const [severities, setSeverities] = useState<string[]>([]);
  // Empty string means "all brands". Five overlapping lines is a legible
  // chart only when you already know what you are looking for; picking one
  // brand is what makes a trend readable.
  const [brand, setBrand] = useState('');

  const window = { date_from: range.from || undefined, date_to: range.to || undefined };
  const brandFilter = brand ? [brand] : undefined;

  const brands = useBrands(window);
  const sentiment = useSentimentTrends({ ...window, brand: brandFilter });
  const topics = useTopicTrends({ ...window, brand: brandFilter });
  const anomalies = useAnomalies({
    ...window,
    severity: severities.length > 0 ? severities : undefined,
    page_size: 50,
  });

  const brandNames = useMemo(
    () => (brands.data ?? []).map((summary) => summary.brand),
    [brands.data],
  );

  /** Pivot per-brand series into one row per date, one column per brand. */
  const sentimentRows = useMemo(() => {
    const byDate = new Map<string, Record<string, string | number | null>>();
    for (const series of sentiment.data?.series ?? []) {
      for (const point of series.points) {
        const row = byDate.get(point.metric_date) ?? { metric_date: point.metric_date };
        row[series.brand] = point.negative_percentage ?? null;
        byDate.set(point.metric_date, row);
      }
    }
    return [...byDate.values()].sort((a, b) =>
      String(a.metric_date).localeCompare(String(b.metric_date)),
    );
  }, [sentiment.data]);

  const sentimentSeries: SeriesSpec[] = useMemo(
    () =>
      (sentiment.data?.series ?? []).map((series, index) => ({
        dataKey: series.brand,
        label: series.brand,
        color: seriesColor(index),
      })),
    [sentiment.data],
  );

  const topTopics = useMemo(
    () => (topics.data?.series ?? []).slice(0, TOPIC_LINE_LIMIT),
    [topics.data],
  );

  const topicRows = useMemo(() => {
    const byDate = new Map<string, Record<string, string | number | null>>();
    for (const series of topTopics) {
      for (const point of series.points) {
        const row = byDate.get(point.metric_date) ?? { metric_date: point.metric_date };
        row[series.topic] = point.review_count;
        byDate.set(point.metric_date, row);
      }
    }
    return [...byDate.values()].sort((a, b) =>
      String(a.metric_date).localeCompare(String(b.metric_date)),
    );
  }, [topTopics]);

  const topicSeries: SeriesSpec[] = useMemo(
    () =>
      topTopics.map((series, index) => ({
        dataKey: series.topic,
        label: series.topic,
        color: seriesColor(index),
      })),
    [topTopics],
  );

  function toggleSeverity(value: string): void {
    setSeverities((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <Card>
        <CardHeader
          title="Negative sentiment over time"
          description={
            brand
              ? `${brand} — share of negative reviews per day`
              : 'Share of negative reviews per brand, per day'
          }
          actions={
            <>
              <SelectFilter
                label="Brand"
                value={brand}
                options={brandNames}
                onChange={setBrand}
                allLabel="All brands"
              />
              <DateRangeFilter from={range.from} to={range.to} onChange={setRange} />
            </>
          }
        />
        <CardBody>
          {sentiment.isError ? (
            <ErrorState error={sentiment.error} onRetry={() => void sentiment.refetch()} />
          ) : sentiment.isPending ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <>
              <TimeSeriesChart
                data={sentimentRows}
                xKey="metric_date"
                series={sentimentSeries}
                valueFormatter={(value) => formatPercent(value, 0)}
                height={280}
              />
              <div className="mt-3 flex flex-wrap gap-2">
                {sentimentSeries.map((series) => (
                  <span
                    key={series.dataKey}
                    className="flex items-center gap-1.5 text-2xs text-ink-muted"
                  >
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ background: series.color ?? token('accent') }}
                    />
                    {series.label}
                  </span>
                ))}
              </div>
            </>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Topic volume"
          description={
            brand
              ? `${brand} — the ${String(TOPIC_LINE_LIMIT)} largest topics by review count`
              : `The ${String(TOPIC_LINE_LIMIT)} largest topics by review count`
          }
          actions={
            topics.data?.fastest_growing != null ? (
              <Badge tone="caution">
                Fastest growing: {topics.data.fastest_growing}
                {topics.data.change_percentage != null
                  ? ` ${topics.data.change_percentage > 0 ? '+' : ''}${topics.data.change_percentage.toFixed(1)}%`
                  : ''}
              </Badge>
            ) : null
          }
        />
        <CardBody>
          {topics.isError ? (
            <ErrorState error={topics.error} onRetry={() => void topics.refetch()} />
          ) : topics.isPending ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <TimeSeriesChart
              data={topicRows}
              xKey="metric_date"
              series={topicSeries}
              valueFormatter={formatCount}
              height={280}
            />
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Anomalies"
          description="Rolling baselines and z-scores — no model, no black box"
          actions={
            <ChipFilter
              label="Severity"
              options={SEVERITIES}
              selected={severities}
              onToggle={toggleSeverity}
            />
          }
        />
        <CardBody className="p-0">
          {anomalies.isError ? (
            <ErrorState error={anomalies.error} onRetry={() => void anomalies.refetch()} />
          ) : anomalies.isPending ? (
            <Skeleton className="m-5 h-40" />
          ) : anomalies.data.items.length === 0 ? (
            <EmptyState
              title="No anomalies match"
              description="Every candidate must clear a minimum volume, a z-score of 2 and a 25% change."
            />
          ) : (
            <ul className="divide-y divide-line">
              {anomalies.data.items.map((anomaly) => (
                <li key={anomaly.id} className="px-5 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={anomaly.severity} />
                    <span className="text-xs font-medium text-ink">{anomaly.brand ?? '—'}</span>
                    <span className="text-2xs text-ink-subtle">{anomaly.detected_date}</span>
                    {anomaly.topic !== null ? (
                      <Badge tone="neutral">{anomaly.topic}</Badge>
                    ) : null}
                  </div>
                  <p className="mt-1 text-xs text-ink-muted">{anomaly.explanation}</p>
                  <div className="mt-1 flex flex-wrap gap-3 text-2xs text-ink-subtle">
                    <span>
                      baseline{' '}
                      {anomaly.baseline_value != null ? anomaly.baseline_value.toFixed(2) : '—'}
                    </span>
                    <span>
                      current{' '}
                      {anomaly.current_value != null ? anomaly.current_value.toFixed(2) : '—'}
                    </span>
                    <span>z {anomaly.z_score != null ? anomaly.z_score.toFixed(2) : '—'}</span>
                    <span>
                      based on {anomaly.review_count != null ? anomaly.review_count : '—'} reviews
                    </span>
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
