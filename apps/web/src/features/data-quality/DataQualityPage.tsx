import type { JSX } from 'react';

import { TimeSeriesChart } from '@/components/charts/TimeSeriesChart';
import { token } from '@/components/charts/chart-theme';
import { Badge } from '@/components/ui/Badge';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { MetricGrid, MetricTile } from '@/components/ui/MetricTile';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { useDataQuality, useQualityTrend } from '@/hooks/useTelemetry';
import { formatCount, formatPercent } from '@/lib/utils';

export function DataQualityPage(): JSX.Element {
  const report = useDataQuality();
  const trend = useQualityTrend();

  const hasRun = report.data?.run_id != null;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <Card>
        <CardHeader
          title="Data quality"
          description={
            report.data?.batch_id != null
              ? `Batch ${report.data.batch_id}`
              : 'Latest pipeline run'
          }
          actions={
            report.data?.quality_score != null ? (
              <Badge tone={report.data.quality_score >= 90 ? 'positive' : 'caution'}>
                score {report.data.quality_score.toFixed(2)}
              </Badge>
            ) : null
          }
        />
        {report.isError ? (
          <ErrorState error={report.error} onRetry={() => void report.refetch()} />
        ) : !report.isPending && !hasRun ? (
          <EmptyState
            title="No pipeline run yet"
            description="Run the pipeline to populate quality results."
          />
        ) : (
          <MetricGrid className="lg:grid-cols-5">
            <MetricTile
              label="Records in"
              value={report.data ? formatCount(report.data.total_records) : null}
              loading={report.isPending}
            />
            <MetricTile
              label="Valid"
              value={report.data ? formatCount(report.data.valid_records) : null}
              loading={report.isPending}
              hint={
                report.data?.validity_rate != null
                  ? formatPercent(report.data.validity_rate)
                  : undefined
              }
            />
            <MetricTile
              label="Quarantined"
              value={report.data ? formatCount(report.data.quarantined_records) : null}
              loading={report.isPending}
              hint="kept, with a reason"
            />
            <MetricTile
              label="Duplicates"
              value={report.data ? formatCount(report.data.duplicate_records) : null}
              loading={report.isPending}
              hint="marked, not deleted"
            />
            <MetricTile
              label="Quality score"
              value={report.data?.quality_score != null ? report.data.quality_score.toFixed(2) : null}
              loading={report.isPending}
              hint="out of 100"
            />
          </MetricGrid>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Validation rules"
          description="Rules that passed are listed too — silence is not the same as success"
        />
        <CardBody className="p-0">
          {report.isPending ? (
            <Skeleton className="m-5 h-40" />
          ) : (report.data?.rules.length ?? 0) === 0 ? (
            <EmptyState title="No rule results recorded" />
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-subtle">
                  <th className="px-5 py-2 font-medium">Rule</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Severity</th>
                  <th className="px-5 py-2 text-right font-medium">Rows affected</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {report.data?.rules.map((rule) => (
                  <tr key={rule.rule_id}>
                    <td className="px-5 py-2.5 font-mono text-ink">{rule.rule_id}</td>
                    <td className="px-3 py-2.5">
                      <Badge tone={rule.status === 'passed' ? 'positive' : 'negative'}>
                        {rule.status}
                      </Badge>
                    </td>
                    <td className="px-3 py-2.5 text-ink-muted">{rule.severity ?? '—'}</td>
                    <td className="px-5 py-2.5 text-right tabular-nums text-ink-muted">
                      {formatCount(rule.affected_rows)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Quality over time"
          description="Score per run — the trend is the point, which is why runs are append-only"
        />
        <CardBody>
          {trend.isError ? (
            <ErrorState error={trend.error} onRetry={() => void trend.refetch()} />
          ) : trend.isPending ? (
            <Skeleton className="h-56 w-full" />
          ) : trend.data.length < 2 ? (
            <EmptyState
              title="Not enough runs to plot a trend"
              description="A trend needs at least two runs. Run the pipeline again to build history."
            />
          ) : (
            <TimeSeriesChart
              data={trend.data.map((point) => ({
                metric_date: point.started_at.slice(0, 10),
                score: point.quality_score,
              }))}
              xKey="metric_date"
              series={[{ dataKey: 'score', label: 'Quality score', color: token('positive') }]}
              valueFormatter={(value) => value.toFixed(1)}
            />
          )}
        </CardBody>
      </Card>
    </div>
  );
}
