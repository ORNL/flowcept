/**
 * TDD tests for inspectorStore — the shared state that drives the Inspector
 * panel when a user clicks a node in any graph visualization.
 *
 * Each graph type sets a different entity kind:
 *   DataflowView (Dataflow tab):
 *     - task node  → kind "task"
 *     - chunk/entity node → kind "dataflow"
 *   DagView (DAG tab):
 *     - task mode → kind "task"
 *     - activity mode → kind "activity"
 *   Objects browser / other surfaces:
 *     - kind "object", kind "chart"
 *
 * All tests run against real store state; no mocks, no DOM.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { useInspectorStore, type InspectorEntity } from "../src/stores/inspectorStore";

function resetStore() {
  useInspectorStore.getState().clear();
}

// ---------------------------------------------------------------------------
// Fixtures — representative data for each entity kind
// ---------------------------------------------------------------------------

function taskEntity(): InspectorEntity {
  return {
    kind: "task",
    data: {
      label: "TrainModel",
      stats: {
        task_id: "t-abc123",
        status: "FINISHED",
        started_at: 1_700_000_000,
        ended_at: 1_700_000_042,
        activity_id: "train",
        custom_metadata: { epoch: 5, loss: 0.03 },
      },
    },
  };
}

function activityEntity(): InspectorEntity {
  return {
    kind: "activity",
    data: {
      label: "PreprocessData",
      stats: {
        task_count: 12,
        avg_duration: 3.7,
        status_counts: { FINISHED: 11, ERROR: 1 },
      },
    },
  };
}

function dataflowChunkEntity(): InspectorEntity {
  return {
    kind: "dataflow",
    data: {
      label: "chunk:0",
      stats: {
        inputs: { X_train: [100, 20] },
        outputs: {},
      },
    },
  };
}

function objectEntity(): InspectorEntity {
  return {
    kind: "object",
    data: {
      object_id: "obj-xyz",
      object_type: "ml_model",
      workflow_id: "wf-1",
      task_id: "t-abc123",
      version: 2,
      object_size_bytes: 4096,
    } as any,
  };
}

function chartEntity(): InspectorEntity {
  return {
    kind: "chart",
    title: "Task Duration per Activity",
    rows: [
      { activity_id: "train", avg_duration: 42 },
      { activity_id: "eval", avg_duration: 8 },
    ],
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("inspectorStore — initial state", () => {
  beforeEach(resetStore);

  it("starts with no selection (null entity)", () => {
    expect(useInspectorStore.getState().entity).toBeNull();
  });
});

describe("inspectorStore — DataflowView clicks (Dataflow tab)", () => {
  beforeEach(resetStore);

  it("clicking a task node sets kind='task' with label and stats", () => {
    useInspectorStore.getState().set(taskEntity());
    const { entity } = useInspectorStore.getState();
    expect(entity?.kind).toBe("task");
    if (entity?.kind === "task") {
      expect(entity.data.label).toBe("TrainModel");
      expect(entity.data.stats.task_id).toBe("t-abc123");
      expect(entity.data.stats.status).toBe("FINISHED");
    }
  });

  it("clicking a chunk/entity node sets kind='dataflow' with label and stats", () => {
    useInspectorStore.getState().set(dataflowChunkEntity());
    const { entity } = useInspectorStore.getState();
    expect(entity?.kind).toBe("dataflow");
    if (entity?.kind === "dataflow") {
      expect(entity.data.label).toBe("chunk:0");
      expect(entity.data.stats.inputs).toBeDefined();
    }
  });
});

describe("inspectorStore — DagView clicks (DAG tab)", () => {
  beforeEach(resetStore);

  it("clicking a node in task mode sets kind='task' with task stats", () => {
    useInspectorStore.getState().set(taskEntity());
    const { entity } = useInspectorStore.getState();
    expect(entity?.kind).toBe("task");
    if (entity?.kind === "task") {
      expect(entity.data.stats.activity_id).toBe("train");
    }
  });

  it("clicking a node in activity mode sets kind='activity' with aggregated stats", () => {
    useInspectorStore.getState().set(activityEntity());
    const { entity } = useInspectorStore.getState();
    expect(entity?.kind).toBe("activity");
    if (entity?.kind === "activity") {
      expect(entity.data.label).toBe("PreprocessData");
      expect(entity.data.stats.task_count).toBe(12);
      expect(entity.data.stats.status_counts).toEqual({ FINISHED: 11, ERROR: 1 });
    }
  });
});

describe("inspectorStore — other entity kinds", () => {
  beforeEach(resetStore);

  it("object entities carry object_id, object_type, version, and size", () => {
    useInspectorStore.getState().set(objectEntity());
    const { entity } = useInspectorStore.getState();
    expect(entity?.kind).toBe("object");
    if (entity?.kind === "object") {
      expect(entity.data.object_id).toBe("obj-xyz");
      expect(entity.data.object_type).toBe("ml_model");
      expect(entity.data.version).toBe(2);
      expect(entity.data.object_size_bytes).toBe(4096);
    }
  });

  it("chart entities carry title and rows", () => {
    useInspectorStore.getState().set(chartEntity());
    const { entity } = useInspectorStore.getState();
    expect(entity?.kind).toBe("chart");
    if (entity?.kind === "chart") {
      expect(entity.title).toBe("Task Duration per Activity");
      expect(entity.rows).toHaveLength(2);
      expect(entity.rows[0].activity_id).toBe("train");
    }
  });
});

describe("inspectorStore — selection lifecycle", () => {
  beforeEach(resetStore);

  it("clear() resets entity to null", () => {
    useInspectorStore.getState().set(taskEntity());
    useInspectorStore.getState().clear();
    expect(useInspectorStore.getState().entity).toBeNull();
  });

  it("clear() is safe to call when already null", () => {
    expect(() => useInspectorStore.getState().clear()).not.toThrow();
    expect(useInspectorStore.getState().entity).toBeNull();
  });

  it("selecting a new entity replaces the previous one", () => {
    useInspectorStore.getState().set(taskEntity());
    useInspectorStore.getState().set(activityEntity());
    const { entity } = useInspectorStore.getState();
    expect(entity?.kind).toBe("activity");
  });

  it("switching from dataflow kind to task kind works correctly", () => {
    useInspectorStore.getState().set(dataflowChunkEntity());
    useInspectorStore.getState().set(taskEntity());
    const { entity } = useInspectorStore.getState();
    expect(entity?.kind).toBe("task");
    if (entity?.kind === "task") {
      expect(entity.data.label).toBe("TrainModel");
    }
  });
});
