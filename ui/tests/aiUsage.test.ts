import { describe, expect, it } from "vitest";
import { getAiModelUsageRows } from "../src/lib/aiUsage";
import type { Task } from "../src/api/types";

describe("getAiModelUsageRows", () => {
  it("extracts normalized LLM usage rows from ai_model_invocation tasks", () => {
    const tasks: Task[] = [
      {
        task_id: "task-1",
        subtype: "ai_model_invocation",
        activity_id: "llm_interaction",
        started_at: 10,
        ended_at: 12,
        custom_metadata: {
          llm_usage: {
            model: "gpt-oss-120b",
            input_tokens: 100,
            output_tokens: 12,
            total_tokens: 112,
            token_count_source: "provider",
            finish_reason: "stop",
            provider_request_id: "chatcmpl-1",
          },
        },
        used: { prompt: "What happened in this workflow?".repeat(10) },
        generated: { response: "The workflow finished successfully.".repeat(10) },
      },
      { task_id: "task-2", subtype: "agent_tool" },
    ];

    const rows = getAiModelUsageRows(tasks);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      task_id: "task-1",
      model: "gpt-oss-120b",
      input_tokens: 100,
      output_tokens: 12,
      total_tokens: 112,
      provider_request_id: "chatcmpl-1",
      token_count_source: "provider",
    });
    expect(rows[0].prompt_preview.length).toBeLessThanOrEqual(143);
    expect(rows[0].response_preview.length).toBeLessThanOrEqual(143);
    expect(rows[0].duration).toBe(2);
  });

  it("marks estimated token counts when providers do not report usage", () => {
    const rows = getAiModelUsageRows([
      {
        task_id: "task-1",
        subtype: "ai_model_invocation",
        custom_metadata: {
          llm_usage: {
            model: "local-model",
            input_tokens: 10,
            output_tokens: 5,
            total_tokens: 15,
            token_count_source: "estimated_from_chars",
          },
        },
      },
    ]);

    expect(rows[0].input_tokens_label).toBe("≈10");
    expect(rows[0].output_tokens_label).toBe("≈5");
    expect(rows[0].total_tokens_label).toBe("≈15");
  });
});
