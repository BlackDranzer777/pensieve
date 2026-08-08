import { useState, type JSX } from 'react';

import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { usePipelineRun, usePipelineRuns } from '@/hooks/useTelemetry';
import { formatCount, formatDuration } from '@/lib/utils';

function statusTone(status: string): BadgeTone {
  if (status === 'success') return 'positive';
  if (status === 'failed') return 'negative';
  if (status === 'partial') return 'caution';
  return 'neutral';
}

export function PipelineRunsPage(): JSX.Element {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const runs = usePipelineRuns();
  const detail = usePipelineRun(selectedId);

  /** Longest stage in the selected run — the bar widths are relative to it. */
  const longestStage = Math.max(
    ...(detail.data?.stages.map((stage) => stage.duration_seconds ?? 0) ?? [0]),
    0.001,
  );

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <Card>
        <CardHeader
          title="Pipeline runs"
          description="Append-only history. Select a run to see its stage timeline."
        />
        <CardBody className="p-0">
          {runs.isError ? (
            <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />
          ) : runs.isPending ? (
            <Skeleton className="m-5 h-40" />
          ) : runs.data.items.length === 0 ? (
            <EmptyState
              title="No runs recorded"
              description="Run the pipeline, then load the results into PostgreSQL."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-subtle">
                    <th className="px-5 py-2 font-medium">Started</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 text-right font-medium">Rows in</th>
                    <th className="px-3 py-2 text-right font-medium">Rows out</th>
                    <th className="px-3 py-2 text-right font-medium">Quarantined</th>
                    <th className="px-3 py-2 text-right font-medium">Duration</th>
                    <th className="px-5 py-2 text-right font-medium">Rows/sec</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {runs.data.items.map((run) => (
                    <tr
                      key={run.id}
                      onClick={() => setSelectedId(run.id)}
                      className="cursor-pointer hover:bg-ink/[0.03]"
                    >
                      <td className="px-5 py-2.5 text-ink">
                        {run.started_at.slice(0, 19).replace('T', ' ')}
                        {run.batch_id !== null ? (
                          <span className="block font-mono text-2xs text-ink-subtle">
                            {run.batch_id}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-3 py-2.5">
                        <Badge tone={statusTone(run.status)}>{run.status}</Badge>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">
                        {formatCount(run.input_rows)}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">
                        {formatCount(run.output_rows)}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">
                        {formatCount(run.quarantined_rows)}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-ink-muted">
                        {run.duration_seconds != null ? formatDuration(run.duration_seconds) : '—'}
                      </td>
                      <td className="px-5 py-2.5 text-right tabular-nums text-ink-muted">
                        {run.rows_per_second != null ? formatCount(run.rows_per_second) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      {selectedId !== null ? (
        <Card>
          <CardHeader
            title="Stage timeline"
            description="Where the time actually went"
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
            ) : detail.data.stages.length === 0 ? (
              <EmptyState title="No stage detail recorded for this run" />
            ) : (
              <ul className="space-y-2.5">
                {detail.data.stages.map((stage) => {
                  const seconds = stage.duration_seconds ?? 0;
                  return (
                    <li key={stage.stage_name} className="text-xs">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium text-ink">{stage.stage_name}</span>
                        <span className="flex items-center gap-2 text-2xs text-ink-subtle">
                          {stage.rows_in != null && stage.rows_out != null ? (
                            <span>
                              {formatCount(stage.rows_in)} → {formatCount(stage.rows_out)}
                            </span>
                          ) : null}
                          {stage.retry_count > 0 ? (
                            <Badge tone="caution">{stage.retry_count} retries</Badge>
                          ) : null}
                          <Badge tone={statusTone(stage.status)}>{stage.status}</Badge>
                          <span className="w-16 text-right tabular-nums text-ink-muted">
                            {formatDuration(seconds)}
                          </span>
                        </span>
                      </div>
                      {/* Width is relative to the slowest stage, so the bar
                          answers "what dominated this run" at a glance. */}
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink/5">
                        <div
                          className="h-full rounded-full bg-accent"
                          style={{ width: `${String((seconds / longestStage) * 100)}%` }}
                        />
                      </div>
                      {stage.error_message !== null ? (
                        <p className="mt-1 text-2xs text-negative">{stage.error_message}</p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}
