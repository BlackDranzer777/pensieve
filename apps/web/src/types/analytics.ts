import { z } from 'zod';

/**
 * Mirrors apps/api/app/schemas/analytics.py.
 *
 * Nullable is used liberally and deliberately. The API returns `null` rather
 * than `0` for a percentage with no denominator — "0% of no reviews" is not a
 * fact — so the schema has to admit it and the UI has to render a dash.
 */

export const brandSummarySchema = z.object({
  brand_id: z.string(),
  brand: z.string(),
  review_count: z.number().int(),
  average_rating: z.number().nullable(),
  positive_count: z.number().int(),
  neutral_count: z.number().int(),
  negative_count: z.number().int(),
  positive_percentage: z.number().nullable(),
  negative_percentage: z.number().nullable(),
  average_sentiment_score: z.number().nullable(),
});

export const brandComparisonSchema = z.object({
  brands: z.array(brandSummarySchema),
  date_from: z.string().nullable(),
  date_to: z.string().nullable(),
  total_reviews: z.number().int(),
});

export const sentimentTrendPointSchema = z.object({
  metric_date: z.string(),
  review_count: z.number().int(),
  negative_count: z.number().int(),
  average_rating: z.number().nullable().optional(),
  negative_percentage: z.number().nullable().optional(),
  average_sentiment_score: z.number().nullable().optional(),
  negative_percentage_7d: z.number().nullable().optional(),
  review_count_7d: z.number().nullable().optional(),
});

export const brandSeriesSchema = z.object({
  brand_id: z.string(),
  brand: z.string(),
  points: z.array(sentimentTrendPointSchema),
});

export const sentimentTrendsSchema = z.object({
  series: z.array(brandSeriesSchema),
  date_from: z.string().nullable(),
  date_to: z.string().nullable(),
});

export const topicPointSchema = z.object({
  metric_date: z.string(),
  topic: z.string(),
  review_count: z.number().int(),
  negative_count: z.number().int(),
  negative_percentage: z.number().nullable().optional(),
  average_sentiment_score: z.number().nullable().optional(),
});

export const topicSeriesSchema = z.object({
  topic: z.string(),
  total_reviews: z.number().int(),
  points: z.array(topicPointSchema),
});

export const topicTrendsSchema = z.object({
  series: z.array(topicSeriesSchema),
  fastest_growing: z.string().nullable(),
  change_percentage: z.number().nullable(),
  date_from: z.string().nullable(),
  date_to: z.string().nullable(),
});

export const countryPointSchema = z.object({
  country: z.string(),
  review_count: z.number().int(),
  average_rating: z.number().nullable(),
  negative_count: z.number().int(),
  negative_percentage: z.number().nullable(),
});

export const languagePointSchema = z.object({
  language: z.string(),
  review_count: z.number().int(),
  percentage: z.number(),
  average_confidence: z.number().nullable(),
});

export const anomalySeveritySchema = z.enum(['low', 'medium', 'high', 'critical']);

export const anomalySchema = z.object({
  id: z.string(),
  anomaly_key: z.string(),
  brand: z.string().nullable(),
  detected_date: z.string(),
  metric: z.string(),
  topic: z.string().nullable(),
  country: z.string().nullable(),
  current_value: z.number().nullable(),
  baseline_value: z.number().nullable(),
  percentage_change: z.number().nullable(),
  z_score: z.number().nullable(),
  review_count: z.number().int().nullable(),
  // Not the enum: an unrecognised severity from a newer backend should render
  // as itself rather than fail the whole response and blank the page.
  severity: z.string(),
  explanation: z.string().nullable(),
  detected_at: z.string().nullable(),
});

export const overviewKpisSchema = z.object({
  total_reviews: z.number().int(),
  non_duplicate_reviews: z.number().int(),
  brands: z.number().int(),
  languages: z.number().int(),
  countries: z.number().int(),
  average_rating: z.number().nullable(),
  positive_percentage: z.number().nullable(),
  negative_percentage: z.number().nullable(),
  earliest_review: z.string().nullable(),
  latest_review: z.string().nullable(),
});

export const topicShareSchema = z.object({
  topic: z.string(),
  review_count: z.number().int(),
  percentage: z.number(),
});

export const overviewSchema = z.object({
  kpis: overviewKpisSchema,
  sentiment_mix: z.record(z.string(), z.number().int()),
  top_topics: z.array(topicShareSchema),
  languages: z.array(languagePointSchema),
  active_anomalies: z.array(anomalySchema),
  latest_quality_score: z.number().nullable(),
  last_run_at: z.string().nullable(),
  last_run_status: z.string().nullable(),
});

export type BrandSummary = z.infer<typeof brandSummarySchema>;
export type BrandComparison = z.infer<typeof brandComparisonSchema>;
export type SentimentTrendPoint = z.infer<typeof sentimentTrendPointSchema>;
export type BrandSeries = z.infer<typeof brandSeriesSchema>;
export type SentimentTrends = z.infer<typeof sentimentTrendsSchema>;
export type TopicPoint = z.infer<typeof topicPointSchema>;
export type TopicSeries = z.infer<typeof topicSeriesSchema>;
export type TopicTrends = z.infer<typeof topicTrendsSchema>;
export type CountryPoint = z.infer<typeof countryPointSchema>;
export type LanguagePoint = z.infer<typeof languagePointSchema>;
export type Anomaly = z.infer<typeof anomalySchema>;
export type OverviewKpis = z.infer<typeof overviewKpisSchema>;
export type TopicShare = z.infer<typeof topicShareSchema>;
export type Overview = z.infer<typeof overviewSchema>;
