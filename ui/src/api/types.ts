/** Hand-maintained API types for the MVP (regenerable later via `npm run gen-api-types`). */

export interface ListResponse<T = Record<string, unknown>> {
  items: T[];
  count: number;
  limit: number;
}

export interface Workflow {
  workflow_id: string;
  name?: string;
  campaign_id?: string;
  parent_workflow_id?: string;
  user?: string;
  utc_timestamp?: number;
  flowcept_version?: string;
  sys_name?: string;
  environment_id?: string;
  workflow_description?: string;
  code_repository?: Record<string, unknown>;
  used?: Record<string, unknown>;
  generated?: Record<string, unknown>;
  custom_metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface Task {
  task_id: string;
  workflow_id?: string;
  parent_task_id?: string;
  campaign_id?: string;
  activity_id?: string;
  agent_id?: string;
  status?: string;
  subtype?: string;
  hostname?: string;
  user?: string;
  started_at?: number | string;
  ended_at?: number | string;
  utc_timestamp?: number | string;
  registered_at?: number | string;
  used?: Record<string, unknown>;
  generated?: Record<string, unknown>;
  stdout?: unknown;
  stderr?: unknown;
  tags?: string[];
  telemetry_at_start?: Record<string, unknown>;
  telemetry_at_end?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface BlobObjectDoc {
  object_id: string;
  workflow_id?: string;
  task_id?: string;
  object_type?: string;
  version?: number;
  object_size_bytes?: number;
  custom_metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface Campaign {
  campaign_id: string;
  workflow_count: number;
  task_count: number;
  users: string[];
  workflow_names: string[];
  first_ts?: number | null;
  last_ts?: number | null;
}

export interface AgentSummary {
  agent_id: string;
  task_count: number;
  activities: string[];
  source_agent_ids: string[];
  campaign_ids: string[];
  last_active?: number | null;
}

export interface ActivityStat {
  activity_id: string | null;
  count: number;
  status_counts: Record<string, number>;
  avg_duration?: number | null;
  min_duration?: number | null;
  max_duration?: number | null;
  sum_duration?: number | null;
}

export interface TaskSummary {
  count: number;
  status_counts: Record<string, number>;
  activity_stats: ActivityStat[];
  time_range: { min_started_at?: number | null; max_ended_at?: number | null };
}

export interface QueryRequest {
  filter?: Record<string, unknown>;
  projection?: string[];
  limit?: number;
  sort?: { field: string; order: 1 | -1 }[];
}

export interface ChartDataResult {
  rows: Record<string, unknown>[];
  count: number;
}
