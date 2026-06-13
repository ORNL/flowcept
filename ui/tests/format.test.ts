/**
 * TDD tests for format helpers — the pure utility functions used across list
 * pages and chart views for timestamp normalization, duration formatting, and
 * workflow sort ordering.
 */

import { describe, it, expect } from "vitest";
import {
  toEpochSec,
  taskDuration,
  fmtDuration,
  fmtBytes,
  shortId,
  agentColor,
  applyNodePositions,
  type TimeValue,
} from "../src/lib/format";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function sampleWorkflows() {
  return [
    { workflow_id: "wf-old", name: "old run", utc_timestamp: 1_700_000_000 },
    { workflow_id: "wf-new", name: "new run", utc_timestamp: 1_750_000_000 },
    { workflow_id: "wf-mid", name: "mid run", utc_timestamp: 1_720_000_000 },
  ];
}

// ---------------------------------------------------------------------------
// toEpochSec
// ---------------------------------------------------------------------------

describe("toEpochSec", () => {
  it("returns null for null input", () => {
    expect(toEpochSec(null)).toBeNull();
  });

  it("returns null for undefined input", () => {
    expect(toEpochSec(undefined)).toBeNull();
  });

  it("returns null for empty string", () => {
    expect(toEpochSec("")).toBeNull();
  });

  it("passes through a number already in epoch-second range", () => {
    expect(toEpochSec(1_700_000_000)).toBe(1_700_000_000);
  });

  it("divides by 1000 when the number looks like epoch milliseconds (> 1e12)", () => {
    expect(toEpochSec(1_700_000_000_000)).toBe(1_700_000_000);
  });

  it("parses an ISO datetime string with Z suffix", () => {
    const sec = toEpochSec("2024-01-15T12:00:00Z");
    expect(sec).not.toBeNull();
    expect(sec).toBeCloseTo(1_705_320_000, -2);
  });

  it("treats an ISO datetime string without timezone as UTC", () => {
    const withZ = toEpochSec("2024-01-15T12:00:00Z");
    const withoutZ = toEpochSec("2024-01-15T12:00:00");
    expect(withZ).toBe(withoutZ);
  });

  it("returns null for a non-parseable string", () => {
    expect(toEpochSec("not-a-date")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// taskDuration
// ---------------------------------------------------------------------------

describe("taskDuration", () => {
  it("returns elapsed seconds when both timestamps are present", () => {
    expect(taskDuration({ started_at: 1000.0, ended_at: 1005.5 })).toBeCloseTo(5.5);
  });

  it("returns null when started_at is missing", () => {
    expect(taskDuration({ ended_at: 1005.0 })).toBeNull();
  });

  it("returns null when ended_at is missing", () => {
    expect(taskDuration({ started_at: 1000.0 })).toBeNull();
  });

  it("returns null when both are missing", () => {
    expect(taskDuration({})).toBeNull();
  });

  it("handles ISO string timestamps", () => {
    const dur = taskDuration({ started_at: "2024-01-15T12:00:00Z", ended_at: "2024-01-15T12:00:10Z" });
    expect(dur).toBeCloseTo(10.0, 1);
  });
});

// ---------------------------------------------------------------------------
// fmtDuration
// ---------------------------------------------------------------------------

describe("fmtDuration", () => {
  it("formats sub-second durations as milliseconds", () => {
    expect(fmtDuration(0.5)).toBe("500 ms");
  });

  it("formats seconds with two decimal places", () => {
    expect(fmtDuration(3.14)).toBe("3.14 s");
  });

  it("formats minutes and seconds", () => {
    expect(fmtDuration(90)).toBe("1m 30s");
  });

  it("formats hours and minutes", () => {
    expect(fmtDuration(3661)).toBe("1h 1m");
  });

  it("returns dash for null", () => {
    expect(fmtDuration(null)).toBe("—");
  });

  it("returns dash for negative duration", () => {
    expect(fmtDuration(-1)).toBe("—");
  });
});

// ---------------------------------------------------------------------------
// fmtBytes
// ---------------------------------------------------------------------------

describe("fmtBytes", () => {
  it("formats raw bytes below 1024", () => {
    expect(fmtBytes(512)).toBe("512 B");
  });

  it("formats kilobytes", () => {
    expect(fmtBytes(2048)).toBe("2.0 KB");
  });

  it("formats megabytes", () => {
    expect(fmtBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("returns dash for null", () => {
    expect(fmtBytes(null)).toBe("—");
  });

  it("returns dash for negative bytes", () => {
    expect(fmtBytes(-1)).toBe("—");
  });
});

// ---------------------------------------------------------------------------
// shortId
// ---------------------------------------------------------------------------

describe("shortId", () => {
  it("truncates long ids and appends ellipsis", () => {
    expect(shortId("abcdef1234567890", 8)).toBe("abcdef12…");
  });

  it("returns the id unchanged when it fits within n+2 chars", () => {
    expect(shortId("short", 8)).toBe("short");
  });

  it("returns dash for null or undefined", () => {
    expect(shortId(null)).toBe("—");
    expect(shortId(undefined)).toBe("—");
  });
});

// ---------------------------------------------------------------------------
// Workflow sort ordering (the logic embedded in useVisibleWorkflows)
// ---------------------------------------------------------------------------

describe("workflow sort ordering (newest-first)", () => {
  it("sorts workflows descending by utc_timestamp", () => {
    const workflows = sampleWorkflows();
    const sorted = [...workflows].sort(
      (a, b) => (toEpochSec(b.utc_timestamp) ?? 0) - (toEpochSec(a.utc_timestamp) ?? 0),
    );
    expect(sorted[0].workflow_id).toBe("wf-new");
    expect(sorted[1].workflow_id).toBe("wf-mid");
    expect(sorted[2].workflow_id).toBe("wf-old");
  });

  it("places workflows without a timestamp last", () => {
    const workflows = [
      { workflow_id: "wf-no-ts", name: "no ts", utc_timestamp: undefined as TimeValue },
      { workflow_id: "wf-ts", name: "has ts", utc_timestamp: 1_700_000_000 },
    ];
    const sorted = [...workflows].sort(
      (a, b) => (toEpochSec(b.utc_timestamp) ?? 0) - (toEpochSec(a.utc_timestamp) ?? 0),
    );
    expect(sorted[0].workflow_id).toBe("wf-ts");
    expect(sorted[1].workflow_id).toBe("wf-no-ts");
  });
});

// ---------------------------------------------------------------------------
// agentColor
// ---------------------------------------------------------------------------

describe("agentColor", () => {
  it("returns default color when agentId is missing", () => {
    expect(agentColor(null)).toBe("#7c3aed");
    expect(agentColor(undefined)).toBe("#7c3aed");
  });

  it("returns a hex color string for valid agent IDs", () => {
    const color = agentColor("agent-1");
    expect(color).toMatch(/^#[0-9a-fA-F]{6}$/);
  });

  it("returns deterministic color for the same agent ID", () => {
    expect(agentColor("agent-1")).toBe(agentColor("agent-1"));
  });

  it("circulates across multiple colors for different IDs", () => {
    const colors = new Set<string>();
    for (let i = 0; i < 50; i++) {
      colors.add(agentColor(`agent-${i}`));
    }
    // We expect multiple colors to be used, not just one or two
    expect(colors.size).toBeGreaterThan(5);
  });
});

// ---------------------------------------------------------------------------
// applyNodePositions
// ---------------------------------------------------------------------------

describe("applyNodePositions", () => {
  it("merges custom positions into nodes if present", () => {
    const nodes = [
      { id: "1", position: { x: 0, y: 0 } },
      { id: "2", position: { x: 10, y: 10 } },
    ] as any[];
    const positions = {
      "1": { x: 100, y: 200 },
    };
    const result = applyNodePositions(nodes, positions);
    expect(result[0].position).toEqual({ x: 100, y: 200 });
    expect(result[1].position).toEqual({ x: 10, y: 10 });
  });

  it("handles empty or missing positions gracefully", () => {
    const nodes = [
      { id: "1", position: { x: 0, y: 0 } },
    ] as any[];
    const result = applyNodePositions(nodes, null as any);
    expect(result[0].position).toEqual({ x: 0, y: 0 });
  });
});

// ---------------------------------------------------------------------------
// getAssociatedAgents
// ---------------------------------------------------------------------------

describe("getAssociatedAgents", () => {
  it("returns unique associated agents (both upstream and downstream)", () => {
    const { getAssociatedAgents } = require("../src/lib/format");
    const agentA = { agent_id: "agent-a", source_agent_ids: ["agent-b"] };
    const agentB = { agent_id: "agent-b", source_agent_ids: [] };
    const agentC = { agent_id: "agent-c", source_agent_ids: ["agent-a"] };
    const agentD = { agent_id: "agent-d", source_agent_ids: [] };
    const allAgents = [agentA, agentB, agentC, agentD] as any[];

    const assoc = getAssociatedAgents(agentA, allAgents);
    const ids = assoc.map((a: any) => a.agent_id);
    expect(ids).toContain("agent-b"); // Upstream
    expect(ids).toContain("agent-c"); // Downstream
    expect(ids).not.toContain("agent-d"); // Unrelated
    expect(ids).not.toContain("agent-a"); // Self
    expect(assoc).toHaveLength(2);
  });
});

