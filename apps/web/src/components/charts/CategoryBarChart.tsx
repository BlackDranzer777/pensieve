import type { JSX } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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

  return (
    <div className="text-ink-subtle" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
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
            formatter={(value: number | string) =>
              typeof value === 'number' ? format(value) : value
            }
          />
          <Bar dataKey="value" radius={3} isAnimationActive={false}>
            {data.map((datum) => (
              <Cell key={datum.label} fill={datum.color ?? accent} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
