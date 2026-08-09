import type { ChangeEvent, JSX } from 'react';

import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

const fieldClasses =
  'rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink ' +
  'focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:opacity-50';

interface DateRangeFilterProps {
  from: string;
  to: string;
  onChange: (next: { from: string; to: string }) => void;
  className?: string;
}

/**
 * Two native date inputs.
 *
 * Native rather than a custom picker: they are keyboard accessible, localised
 * and screen-reader friendly for free, which a hand-rolled calendar would have
 * to earn back one accessibility bug at a time.
 */
export function DateRangeFilter({
  from,
  to,
  onChange,
  className,
}: DateRangeFilterProps): JSX.Element {
  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      <label className="sr-only" htmlFor="date-from">
        From date
      </label>
      <input
        id="date-from"
        type="date"
        value={from}
        // `max` stops the inverted range at the source. The API rejects it too,
        // but an input that cannot express the mistake beats an error message.
        max={to || undefined}
        onChange={(event: ChangeEvent<HTMLInputElement>) =>
          { onChange({ from: event.target.value, to }); }
        }
        className={fieldClasses}
      />
      <span className="text-2xs text-ink-subtle">to</span>
      <label className="sr-only" htmlFor="date-to">
        To date
      </label>
      <input
        id="date-to"
        type="date"
        value={to}
        min={from || undefined}
        onChange={(event: ChangeEvent<HTMLInputElement>) =>
          { onChange({ from, to: event.target.value }); }
        }
        className={fieldClasses}
      />
      {from || to ? (
        <button
          type="button"
          onClick={() => { onChange({ from: '', to: '' }); }}
          className="rounded-md px-1.5 py-1 text-2xs text-ink-muted hover:bg-ink/5"
        >
          Clear
        </button>
      ) : null}
    </div>
  );
}

interface SelectFilterProps {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
  /** Shown as the "no filter" option. */
  allLabel?: string;
  className?: string;
}

export function SelectFilter({
  label,
  value,
  options,
  onChange,
  allLabel = 'All',
  className,
}: SelectFilterProps): JSX.Element {
  return (
    <label className={cn('flex items-center gap-1.5 text-2xs text-ink-muted', className)}>
      {label}
      <select
        value={value}
        onChange={(event) => { onChange(event.target.value); }}
        className={fieldClasses}
      >
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

interface ChipFilterProps {
  label: string;
  options: readonly string[];
  selected: readonly string[];
  onToggle: (value: string) => void;
  className?: string;
}

/**
 * Multi-select as toggleable chips.
 *
 * A `<select multiple>` is the obvious alternative and is genuinely awful to
 * use — it needs ctrl-click, hides the selection, and is nearly unusable on
 * touch. Chips make the current filter visible at a glance, which matters when
 * the question is "why does this table look wrong".
 */
export function ChipFilter({
  label,
  options,
  selected,
  onToggle,
  className,
}: ChipFilterProps): JSX.Element {
  return (
    <fieldset className={cn('min-w-0', className)}>
      <legend className="text-2xs font-medium uppercase tracking-wide text-ink-subtle">
        {label}
      </legend>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {options.map((option) => {
          const active = selected.includes(option);
          return (
            <button
              key={option}
              type="button"
              aria-pressed={active}
              onClick={() => { onToggle(option); }}
              className={cn(
                'rounded-full px-2 py-0.5 text-2xs ring-1 ring-inset transition-colors',
                active
                  ? 'bg-accent/10 text-accent ring-accent/30'
                  : 'bg-surface text-ink-muted ring-line hover:bg-ink/5',
              )}
            >
              {option}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
  className,
}: SearchInputProps): JSX.Element {
  return (
    <div className={cn('relative', className)}>
      <label className="sr-only" htmlFor="review-search">
        Search reviews
      </label>
      <input
        id="review-search"
        type="search"
        value={value}
        onChange={(event) => { onChange(event.target.value); }}
        placeholder={placeholder}
        className={cn(fieldClasses, 'w-full py-1.5')}
      />
    </div>
  );
}

interface PaginationBarProps {
  page: number;
  totalPages: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  className?: string;
}

export function PaginationBar({
  page,
  totalPages,
  totalItems,
  onPageChange,
  className,
}: PaginationBarProps): JSX.Element {
  const buttonClasses =
    'rounded-md border border-line bg-surface px-2.5 py-1 text-2xs text-ink ' +
    'hover:bg-ink/5 disabled:cursor-not-allowed disabled:opacity-40 transition-colors';

  return (
    <div className={cn('flex items-center justify-between gap-3 px-5 py-3', className)}>
      <p className="text-2xs text-ink-muted">
        Page {page.toLocaleString()} of {totalPages.toLocaleString()}{' '}
        <span className="text-ink-subtle">({totalItems.toLocaleString()} results)</span>
      </p>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          className={buttonClasses}
          disabled={page <= 1}
          onClick={() => { onPageChange(page - 1); }}
        >
          Previous
        </button>
        <button
          type="button"
          className={buttonClasses}
          disabled={page >= totalPages}
          onClick={() => { onPageChange(page + 1); }}
        >
          Next
        </button>
      </div>
    </div>
  );
}

/** Sentiment rendered with the same colour everywhere it appears. */
export function SentimentBadge({ sentiment }: { sentiment: string | null }): JSX.Element {
  if (sentiment === null) return <span className="text-ink-subtle">—</span>;
  const tone =
    sentiment === 'positive' ? 'positive' : sentiment === 'negative' ? 'negative' : 'neutral';
  return <Badge tone={tone}>{sentiment}</Badge>;
}

/** Severity rendered with the same colour everywhere it appears. */
export function SeverityBadge({ severity }: { severity: string }): JSX.Element {
  const tone =
    severity === 'critical' || severity === 'high'
      ? 'negative'
      : severity === 'medium'
        ? 'caution'
        : 'info';
  return <Badge tone={tone}>{severity}</Badge>;
}
