import { z } from 'zod';

/** Mirrors apps/api/app/schemas/reviews.py. */

export const reviewTopicSchema = z.object({
  topic: z.string(),
  is_primary: z.boolean(),
  score: z.number().nullable().optional(),
  matched_keywords: z.string().nullable().optional(),
});

export const reviewListItemSchema = z.object({
  id: z.string(),
  external_review_id: z.string(),
  brand: z.string(),
  product: z.string().nullable(),
  country: z.string().nullable(),
  source: z.string().nullable(),
  rating: z.number().int().nullable(),
  original_text: z.string(),
  language: z.string().nullable(),
  sentiment: z.string().nullable(),
  sentiment_score: z.number().nullable(),
  primary_topic: z.string().nullable(),
  review_created_at: z.string(),
  is_duplicate: z.boolean(),
});

export const reviewDetailSchema = reviewListItemSchema.extend({
  normalized_text: z.string().nullable(),
  language_confidence: z.number().nullable(),
  sentiment_model_version: z.string().nullable(),
  word_count: z.number().int().nullable(),
  is_duplicate_of: z.string().nullable(),
  processed_at: z.string().nullable(),
  topics: z.array(reviewTopicSchema),
});

export const reviewFacetsSchema = z.object({
  brands: z.array(z.string()),
  countries: z.array(z.string()),
  languages: z.array(z.string()),
  sentiments: z.array(z.string()),
  topics: z.array(z.string()),
  sources: z.array(z.string()),
});

export type ReviewTopic = z.infer<typeof reviewTopicSchema>;
export type ReviewListItem = z.infer<typeof reviewListItemSchema>;
export type ReviewDetail = z.infer<typeof reviewDetailSchema>;
export type ReviewFacets = z.infer<typeof reviewFacetsSchema>;

/** Every filter the Review Explorer supports, mirrored in the URL. */
export interface ReviewFilters {
  q?: string;
  brand?: string[];
  country?: string[];
  language?: string[];
  sentiment?: string[];
  source?: string[];
  topic?: string[];
  rating?: number[];
  date_from?: string;
  date_to?: string;
  include_duplicates?: boolean;
  sort?: string;
  order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}
