import type { JSX } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { axisProps, seriesColor, token } from '@/components/charts/chart-theme';
import { EmptyState } from '@/components/ui/States';

export interface SeriesSpec {
  /** Key into each row of `data`. */
  dataKey: string;
  label: string;
  /** Overrides the palette — use for sentiment, where colour carries meaning. */
  color?: string;
  /** Renders dashed. Used for baselines, which are context rather than data. */
  dashed?: boolean;
}

interface TimeSeriesChartProps {
  data: Array<Record<string, string | number | null>>;
  xKey: string;
  series: SeriesSpec[];
  height?: number;
  /** Formats the Y axis and tooltip values. */
  valueFormatter?: (value: number) => string;
  emptyMessage?: string;
}

/** Trim an ISO date to `MM-DD`, which is all an axis has room for. */
function shortDate(value: string): string {
  return value.length >= 10 ? value.slice(5, 10) : value;
}

/**
 * A multi-series line chart over dates.
 *
 * One component for every time series on the site so axes, tooltips and colours
 * cannot drift apart between pages — an analytics UI loses credibility fast
 * when the same metric looks different in two places.
 */
export function TimeSeriesChart({
  data,
  xKey,
  series,
  height = 260,
  valueFormatter,
  emptyMessage = 'No data in this range.',
}: TimeSeriesChartProps): JSX.Element {
  if (data.length === 0) {
    return <EmptyState title="Nothing to chart" description={emptyMessage} />;
  }

  const format = valueFormatter ?? ((value: number): string => String(value));

  return (
    <div className="text-ink-subtle" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={token('line')} strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey={xKey} tickFormatter={shortDate} minTickGap={24} {...axisProps} />
          <YAxis tickFormatter={format} width={56} {...axisProps} />
          <Tooltip
            contentStyle={{
              background: token('surface'),
              border: `1px solid ${token('line')}`,
              borderRadius: 10,
              fontSize: 12,
              color: token('ink'),
            }}
            labelStyle={{ color: token('ink-muted'), fontSize: 11 }}
            formatter={(value: number | string) =>
              typeof value === 'number' ? format(value) : value
            }
          />
          {series.map((spec, index) => (
            <Line
              key={spec.dataKey}
              type="monotone"
              dataKey={spec.dataKey}
              name={spec.label}
              stroke={spec.color ?? seriesColor(index)}
              strokeWidth={1.75}
              strokeDasharray={spec.dashed === true ? '4 3' : undefined}
              dot={false}
              // Gaps stay gaps. Joining across a missing day would draw a
              // straight line through data that does not exist.
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
