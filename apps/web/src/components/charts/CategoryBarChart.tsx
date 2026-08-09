import type { JSX } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { axisProps, token } from '@/components/charts/chart-theme';
import { EmptyState } from '@/components/ui/States';

export interface CategoryDatum {
  label: string;
  value: number;
  /** Overrides the default bar colour for this one category. */
  color?: string;
}

interface CategoryBarChartProps {
  data: CategoryDatum[];
  height?: number;
  valueFormatter?: (value: number) => string;
  /** Horizontal bars — the right choice when labels are words, not dates. */
  horizontal?: boolean;
}

/**
 * A ranked bar chart for categorical data — topics, countries, languages.
 *
 * Defaults to horizontal because the categories here are words. Rotated
 * vertical labels are harder to read and cost more height than the bars.
 */
export function CategoryBarChart({
  data,
  height = 260,
  valueFormatter,
  horizontal = true,
}: CategoryBarChartProps): JSX.Element {
  if (data.length === 0) {
    return <EmptyState title="Nothing to chart" description="No categories in this range." />;
  }

  const format = valueFormatter ?? ((value: number): string => String(value));
  const accent = token('accent');

  // Per-bar colour is carried on the datum as `fill`, which Recharts reads
  // directly. `<Cell>` is the traditional way and is deprecated in Recharts 3.
  const chartData = data.map((datum) => ({ ...datum, fill: datum.color ?? accent }));

  return (
    <div className="text-ink-subtle" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          layout={horizontal ? 'vertical' : 'horizontal'}
          margin={{ top: 4, right: 16, bottom: 0, left: horizontal ? 8 : -12 }}
        >
          <CartesianGrid
            stroke={token('line')}
            strokeDasharray="2 4"
            horizontal={!horizontal}
            vertical={horizontal}
          />
          {horizontal ? (
            <>
              <XAxis type="number" tickFormatter={format} {...axisProps} />
              <YAxis type="category" dataKey="label" width={130} {...axisProps} />
            </>
          ) : (
            <>
              <XAxis type="category" dataKey="label" {...axisProps} />
              <YAxis type="number" tickFormatter={format} width={56} {...axisProps} />
            </>
          )}
          <Tooltip
            cursor={{ fill: token('ink', 0.04) }}
            contentStyle={{
              background: token('surface'),
              border: `1px solid ${token('line')}`,
              borderRadius: 10,
              fontSize: 12,
              color: token('ink'),
            }}
            // See TimeSeriesChart: Recharts 3 types this value as
            // `ValueType | undefined`, so the parameter type must be inferred.
            formatter={(value) => (typeof value === 'number' ? format(value) : String(value ?? ''))}
          />
          <Bar dataKey="value" radius={3} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
