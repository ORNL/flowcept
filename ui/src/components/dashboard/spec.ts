/** Dashboard spec types (mirror of webservice schemas/dashboards.py) + zod validation.
 *
 * Data model:
 *   Dashboard (type: workflow | campaign)
 *     └── Chart[]  — each chart has a data binding + viz spec
 */

import { z } from "zod";

export const metricSpec = z.object({
  field: z.string(),
  agg: z.enum(["avg", "sum", "min", "max", "count"]),
});

export const chartData = z.object({
  source: z.enum(["tasks", "workflows", "objects", "collection_sizes"]).default("tasks"),
  filter: z.record(z.unknown()).default({}),
  group_by: z.string().nullish(),
  metrics: z.array(metricSpec).nullish(),
  x: z.string().nullish(),
  y: z.array(z.string()).nullish(),
  sort: z.array(z.object({ field: z.string(), order: z.union([z.literal(1), z.literal(-1)]) })).nullish(),
  limit: z.number().default(500),
});

export const vizSpec = z.object({
  kind: z.enum(["line", "bar", "pie", "scatter", "area", "heatmap"]).default("line"),
  stacked: z.boolean().default(false),
});

export const chart = z.object({
  chart_id: z.string(),
  type: z.enum(["chart", "metric", "table", "markdown"]),
  title: z.string().default(""),
  live: z.boolean().default(false),
  refresh_interval_sec: z.number().nullish(),
  data: chartData.nullish(),
  viz: vizSpec.nullish(),
  content: z.string().nullish(),
});

export const layoutItem = z.object({
  chart_id: z.string(),
  x: z.number(),
  y: z.number(),
  w: z.number(),
  h: z.number(),
});

export const dashboardSpec = z.object({
  dashboard_id: z.string().nullish(),
  type: z.enum(["workflow", "campaign"]).default("workflow"),
  name: z.string(),
  description: z.string().default(""),
  context: z.record(z.unknown()).default({}),
  charts: z.array(chart).default([]),
  layout: z.array(layoutItem).default([]),
  created_at: z.string().nullish(),
  updated_at: z.string().nullish(),
});

export type MetricSpec = z.infer<typeof metricSpec>;
export type ChartData = z.infer<typeof chartData>;
export type VizSpec = z.infer<typeof vizSpec>;
export type Chart = z.infer<typeof chart>;
export type LayoutItem = z.infer<typeof layoutItem>;
export type DashboardSpec = z.infer<typeof dashboardSpec>;

export function metricKey(m: MetricSpec): string {
  return m.field ? `${m.agg}_${m.field}` : m.agg;
}
