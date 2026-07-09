import type { Task } from "../api/types";
import type { InspectorEntity } from "../stores/inspectorStore";

export function taskToInspectorEntity(task: Task): InspectorEntity {
  return {
    kind: "task",
    data: {
      label: task.activity_id ?? task.task_id,
      stats: {
        ...task,
      },
    },
  };
}
