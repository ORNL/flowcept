/**
 * TDD tests for highlightStore — the Zustand store that drives provenance
 * lineage highlighting across the Dataflow and DAG graph views.
 *
 * Tests exercise real store state transitions; no mocks, no DOM.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { useHighlightStore } from "../src/stores/highlightStore";

function resetStore() {
  useHighlightStore.getState().clearHighlight();
}

describe("highlightStore", () => {
  beforeEach(resetStore);

  it("starts with an empty task-id set", () => {
    expect(useHighlightStore.getState().taskIds.size).toBe(0);
  });

  it("setHighlight populates taskIds with the given ids", () => {
    useHighlightStore.getState().setHighlight(["t1", "t2", "t3"]);
    const { taskIds } = useHighlightStore.getState();
    expect(taskIds.size).toBe(3);
    expect(taskIds.has("t1")).toBe(true);
    expect(taskIds.has("t2")).toBe(true);
    expect(taskIds.has("t3")).toBe(true);
  });

  it("setHighlight replaces the previous set entirely", () => {
    useHighlightStore.getState().setHighlight(["t1", "t2"]);
    useHighlightStore.getState().setHighlight(["t99"]);
    const { taskIds } = useHighlightStore.getState();
    expect(taskIds.size).toBe(1);
    expect(taskIds.has("t99")).toBe(true);
    expect(taskIds.has("t1")).toBe(false);
  });

  it("clearHighlight empties the set", () => {
    useHighlightStore.getState().setHighlight(["t1", "t2"]);
    useHighlightStore.getState().clearHighlight();
    expect(useHighlightStore.getState().taskIds.size).toBe(0);
  });

  it("clearHighlight is safe to call when already empty", () => {
    expect(() => useHighlightStore.getState().clearHighlight()).not.toThrow();
    expect(useHighlightStore.getState().taskIds.size).toBe(0);
  });

  it("setHighlight with an empty array results in an empty set", () => {
    useHighlightStore.getState().setHighlight(["t1"]);
    useHighlightStore.getState().setHighlight([]);
    expect(useHighlightStore.getState().taskIds.size).toBe(0);
  });

  it("setHighlight deduplicates repeated ids", () => {
    useHighlightStore.getState().setHighlight(["t1", "t1", "t1"]);
    expect(useHighlightStore.getState().taskIds.size).toBe(1);
  });

  it("state is shared across multiple getState() calls", () => {
    useHighlightStore.getState().setHighlight(["shared-task"]);
    const s1 = useHighlightStore.getState();
    const s2 = useHighlightStore.getState();
    expect(s1.taskIds).toBe(s2.taskIds);
  });
});
