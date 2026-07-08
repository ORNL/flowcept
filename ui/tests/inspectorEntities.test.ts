import { describe, expect, it } from "vitest";
import type { Task } from "../src/api/types";
import { taskToInspectorEntity } from "../src/lib/inspectorEntities";

describe("taskToInspectorEntity", () => {
  it("maps a task row to the Inspector task entity shape", () => {
    const task: Task = {
      task_id: "task-1",
      activity_id: "train",
      status: "FINISHED",
      agent_id: "agent-1",
      source_agent_id: "agent-0",
      started_at: 100,
      ended_at: 110,
      used: { x: 1 },
      generated: { y: 2 },
    };

    const entity = taskToInspectorEntity(task);

    expect(entity?.kind).toBe("task");
    if (entity?.kind === "task") {
      expect(entity.data.label).toBe("train");
      expect(entity.data.stats.task_id).toBe("task-1");
      expect(entity.data.stats.agent_id).toBe("agent-1");
      expect(entity.data.stats.source_agent_id).toBe("agent-0");
      expect(entity.data.stats.used).toEqual({ x: 1 });
      expect(entity.data.stats.generated).toEqual({ y: 2 });
    }
  });
});
