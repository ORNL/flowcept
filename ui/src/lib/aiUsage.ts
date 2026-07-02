import type { Task } from "../api/types";
import { taskDuration } from "./format";

export const AI_MODEL_INVOCATION_SUBTYPE = "ai_model_invocation";

export interface AiModelUsageRow {
  task_id: string;
  model?: string;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  input_tokens_label: string;
  output_tokens_label: string;
  total_tokens_label: string;
  token_count_source?: string;
  provider_request_id?: string;
  prompt_preview: string;
  response_preview: string;
  duration: number | null;
  started_at?: Task["started_at"];
  task: Task;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function tokenLabel(value: number | undefined, source: string | undefined): string {
  if (value === undefined) return "—";
  return source === "estimated_from_chars" ? `≈${value}` : String(value);
}

function preview(value: unknown, maxLength = 140): string {
  const text = typeof value === "string" ? value : value == null ? "" : JSON.stringify(value);
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length > maxLength ? `${compact.slice(0, maxLength)}…` : compact;
}

export function getAiModelUsageRows(tasks: Task[]): AiModelUsageRow[] {
  return tasks
    .filter((task) => task.subtype === AI_MODEL_INVOCATION_SUBTYPE)
    .map((task) => {
      const metadata = asRecord(task.custom_metadata);
      const usage = asRecord(metadata.llm_usage);
      const inputTokens = asNumber(usage.input_tokens ?? usage.llm_input_tokens);
      const outputTokens = asNumber(usage.output_tokens ?? usage.llm_output_tokens);
      const totalTokens = asNumber(usage.total_tokens ?? usage.llm_total_tokens);
      const tokenCountSource = asString(usage.token_count_source);
      return {
        task_id: task.task_id,
        model: asString(usage.model ?? usage.llm_model),
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        total_tokens: totalTokens,
        input_tokens_label: tokenLabel(inputTokens, tokenCountSource),
        output_tokens_label: tokenLabel(outputTokens, tokenCountSource),
        total_tokens_label: tokenLabel(totalTokens, tokenCountSource),
        token_count_source: tokenCountSource,
        provider_request_id: asString(usage.provider_request_id),
        prompt_preview: preview(asRecord(task.used).prompt),
        response_preview: preview(asRecord(task.generated).response),
        duration: taskDuration(task),
        started_at: task.started_at,
        task,
      };
    });
}
