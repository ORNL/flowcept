/**
 * TDD tests for expandLineage — the BFS that resolves ancestor + descendant
 * lineage for provenance highlight in the Dataflow graph.
 *
 * All tests use plain graph data (no React, no DOM).
 */

import { describe, it, expect } from "vitest";
import { expandLineage, type GraphEdge } from "../src/lib/lineage";

// ---------------------------------------------------------------------------
// Graph fixtures — reusable across tests
// ---------------------------------------------------------------------------

/** Linear chain: A → B → C */
function linearChain(): GraphEdge[] {
  return [
    { source: "A", target: "B" },
    { source: "B", target: "C" },
  ];
}

/** Diamond: A → B, A → C, B → D, C → D */
function diamond(): GraphEdge[] {
  return [
    { source: "A", target: "B" },
    { source: "A", target: "C" },
    { source: "B", target: "D" },
    { source: "C", target: "D" },
  ];
}

/** Two disconnected paths: A → B and X → Y */
function disconnected(): GraphEdge[] {
  return [
    { source: "A", target: "B" },
    { source: "X", target: "Y" },
  ];
}

/** Dataflow-style ids: task nodes and chunk entities */
function dataflowGraph(): GraphEdge[] {
  return [
    { source: "task:t1", target: "chunk:0" },
    { source: "chunk:0", target: "task:t2" },
    { source: "task:t2", target: "chunk:1" },
    { source: "chunk:1", target: "task:t3" },
  ];
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("expandLineage", () => {
  it("returns empty set for empty seeds", () => {
    const result = expandLineage([], linearChain());
    expect(result.size).toBe(0);
  });

  it("includes the seed itself when it has no edges", () => {
    const result = expandLineage(["Z"], linearChain());
    expect(result).toEqual(new Set(["Z"]));
  });

  it("expands to full chain when seeding the middle node", () => {
    // Seed B in A→B→C: backward reaches A, forward reaches C.
    const result = expandLineage(["B"], linearChain());
    expect(result).toEqual(new Set(["A", "B", "C"]));
  });

  it("expands downstream only when seeding the root", () => {
    const result = expandLineage(["A"], linearChain());
    expect(result).toEqual(new Set(["A", "B", "C"]));
  });

  it("expands upstream only when seeding the leaf", () => {
    const result = expandLineage(["C"], linearChain());
    expect(result).toEqual(new Set(["A", "B", "C"]));
  });

  it("does NOT cross to the sibling branch in a diamond when seeding one branch", () => {
    // Seed B in diamond A→B, A→C, B→D, C→D.
    // B's lineage is: ancestors={A}, descendants={D}. C is NOT in B's lineage.
    const result = expandLineage(["B"], diamond());
    expect(result.has("B")).toBe(true);
    expect(result.has("A")).toBe(true); // ancestor via backward BFS
    expect(result.has("D")).toBe(true); // descendant via forward BFS
    expect(result.has("C")).toBe(false); // sibling — must NOT be included
  });

  it("does not bleed into a disconnected subgraph", () => {
    // Seed A in a graph that also has X→Y. Y must not appear.
    const result = expandLineage(["A"], disconnected());
    expect(result).toEqual(new Set(["A", "B"]));
    expect(result.has("X")).toBe(false);
    expect(result.has("Y")).toBe(false);
  });

  it("handles multiple seeds correctly, unioning their lineages", () => {
    // Seeds B and X: B's chain is {A,B} (no C yet since C not in disconnected);
    // X's chain is {X,Y}. Combined = {A,B,X,Y}.
    const result = expandLineage(["B", "X"], disconnected());
    expect(result).toEqual(new Set(["A", "B", "X", "Y"]));
  });

  it("works correctly with dataflow-style task: and chunk: node ids", () => {
    // Seed task:t2 — backward reaches chunk:0 and task:t1; forward reaches chunk:1 and task:t3.
    const result = expandLineage(["task:t2"], dataflowGraph());
    expect(result).toEqual(new Set(["task:t1", "chunk:0", "task:t2", "chunk:1", "task:t3"]));
  });

  it("seeding a chunk entity reaches its producing and consuming tasks", () => {
    const result = expandLineage(["chunk:0"], dataflowGraph());
    expect(result.has("task:t1")).toBe(true);
    expect(result.has("task:t2")).toBe(true);
  });

  it("handles graphs with no edges", () => {
    const result = expandLineage(["A"], []);
    expect(result).toEqual(new Set(["A"]));
  });

  it("is idempotent — calling twice with same args returns equal sets", () => {
    const first = expandLineage(["B"], diamond());
    const second = expandLineage(["B"], diamond());
    expect(first).toEqual(second);
  });

  it("does not mutate the input seeds iterable", () => {
    const seeds = new Set(["B"]);
    expandLineage(seeds, diamond());
    expect(seeds.size).toBe(1);
  });
});
