import { z } from 'zod';

/** Mirrors apps/api/app/schemas/telemetry.py. */

export const stageRunSchema = z.object({
  stage_name: z.string(),
  status: z.string(),
  started_at: z.string(),
  completed_at: z.string().nullable(),
  duration_seconds: z.number().nullable(),
  rows_in: z.number().int().nullable(),
  rows_out: z.number().int().nullable(),
  retry_count: z.number().int(),
  error_message: z.string().nullable(),
});

export const pipelineRunSchema = z.object({
  id: z.string(),
  batch_id: z.string().nullable(),
  status: z.string(),
  started_at: z.string(),
  completed_at: z.string().nullable(),
  duration_seconds: z.number().nullable(),
  input_rows: z.number().int(),
  output_rows: z.number().int(),
  failed_rows: z.number().int(),
  quarantined_rows: z.number().int(),
  duplicate_rows: z.number().int(),
  rows_per_second: z.number().nullable(),
  quality_score: z.number().nullable(),
  error_message: z.string().nullable(),
});

export const pipelineRunDetailSchema = pipelineRunSchema.extend({
  stages: z.array(stageRunSchema),
});

export const qualityRuleResultSchema = z.object({
  rule_id: z.string(),
  check_name: z.string().nullable(),
  status: z.string(),
  severity: z.string().nullable(),
  affected_rows: z.number().int(),
});

export const dataQualityReportSchema = z.object({
  run_id: z.string().nullable(),
  batch_id: z.string().nullable(),
  recorded_at: z.string().nullable(),
  quality_score: z.number().nullable(),
  total_records: z.number().int(),
  valid_records: z.number().int(),
  quarantined_records: z.number().int(),
  duplicate_records: z.number().int(),
  validity_rate: z.number().nullable(),
  rules: z.array(qualityRuleResultSchema),
});

export const qualityTrendPointSchema = z.object({
  run_id: z.string(),
  started_at: z.string(),
  quality_score: z.number().nullable(),
  input_rows: z.number().int(),
  quarantined_rows: z.number().int(),
});

export type StageRun = z.infer<typeof stageRunSchema>;
export type PipelineRun = z.infer<typeof pipelineRunSchema>;
export type PipelineRunDetail = z.infer<typeof pipelineRunDetailSchema>;
export type QualityRuleResult = z.infer<typeof qualityRuleResultSchema>;
export type DataQualityReport = z.infer<typeof dataQualityReportSchema>;
export type QualityTrendPoint = z.infer<typeof qualityTrendPointSchema>;
