/**
 * Shared chart styling.
 *
 * Recharts cannot read Tailwind classes, so colours are resolved from the same
 * CSS custom properties the rest of the UI uses. Hardcoding hex values here
 * would give charts a palette that silently ignores the light/dark toggle.
 */

/** Read a `--color-*` token and return it as a usable `rgb()` string. */
export function token(name: string, alpha = 1): string {
  if (typeof window === 'undefined') return 'rgb(120 120 120)';
  const raw = getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
  if (!raw) return 'rgb(120 120 120)';
  return alpha === 1 ? `rgb(${raw})` : `rgb(${raw} / ${String(alpha)})`;
}

/**
 * Colours for categorical series, in assignment order.
 *
 * Ordered so the first few are distinguishable for the most common forms of
 * colour blindness; sentiment charts should still use the semantic colours
 * below rather than pick from this list.
 */
export const SERIES_TOKENS = ['accent', 'info', 'caution', 'positive', 'negative'] as const;

export function seriesColor(index: number): string {
  return token(SERIES_TOKENS[index % SERIES_TOKENS.length] ?? 'accent');
}

/** Sentiment must always use the same colour, on every chart. */
export const SENTIMENT_TOKENS: Record<string, string> = {
  positive: 'positive',
  neutral: 'ink-subtle',
  negative: 'negative',
  unknown: 'ink-subtle',
};

export function sentimentColor(sentiment: string): string {
  return token(SENTIMENT_TOKENS[sentiment] ?? 'ink-subtle');
}

export const SEVERITY_TOKENS: Record<string, string> = {
  low: 'info',
  medium: 'caution',
  high: 'negative',
  critical: 'negative',
};

/** Axis and grid defaults, applied identically to every chart. */
export const axisProps = {
  stroke: 'currentColor',
  tick: { fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;
