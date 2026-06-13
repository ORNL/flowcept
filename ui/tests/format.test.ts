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
  agentIconStyle,
  applyNodePositions,
  sortAgents,
  sortCampaigns,
  sortWorkflows,
  filterActiveAgents,
  filterGraphEdges,
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
// Entity sorting (newest-first)
// ---------------------------------------------------------------------------

describe("entity sorting (newest-first)", () => {
  it("sortAgents sorts agents descending by most recent timestamp (last_active or registered_at)", () => {
    const a1 = { agent_id: "a1", registered_at: 1000, last_active: 2000 };
    const a2 = { agent_id: "a2", registered_at: 5000, last_active: null };
    const a3 = { agent_id: "a3", registered_at: 3000, last_active: 1000 };
    const sorted = sortAgents([a1, a2, a3] as any[]);
    expect(sorted[0].agent_id).toBe("a2"); // 5000
    expect(sorted[1].agent_id).toBe("a3"); // 3000
    expect(sorted[2].agent_id).toBe("a1"); // 2000
  });

  it("sortCampaigns sorts campaigns descending by most recent timestamp (last_ts or first_ts)", () => {
    const c1 = { campaign_id: "c1", last_ts: 1000, first_ts: 500 };
    const c2 = { campaign_id: "c2", last_ts: 3000, first_ts: 2000 };
    const c3 = { campaign_id: "c3", last_ts: 2000, first_ts: 1500 };
    const sorted = sortCampaigns([c1, c2, c3] as any[]);
    expect(sorted[0].campaign_id).toBe("c2"); // 3000
    expect(sorted[1].campaign_id).toBe("c3"); // 2000
    expect(sorted[2].campaign_id).toBe("c1"); // 1000
  });

  it("sortWorkflows sorts workflows descending by utc_timestamp", () => {
    const workflows = sampleWorkflows();
    const sorted = sortWorkflows(workflows as any[]);
    expect(sorted[0].workflow_id).toBe("wf-new");
    expect(sorted[1].workflow_id).toBe("wf-mid");
    expect(sorted[2].workflow_id).toBe("wf-old");
  });

  it("filterActiveAgents filters out agents with 0 task count", () => {
    const a1 = { agent_id: "a1", task_count: 5 };
    const a2 = { agent_id: "a2", task_count: 0 };
    const a3 = { agent_id: "a3", task_count: 1 };
    const filtered = filterActiveAgents([a1, a2, a3] as any[]);
    expect(filtered).toHaveLength(2);
    expect(filtered.map(x => x.agent_id)).toEqual(["a1", "a3"]);
  });
});

describe("agentIconStyle", () => {
  it("returns default color and stroke when agentId is missing", () => {
    const res = agentIconStyle(null);
    expect(res.color).toBe("#7c3aed");
    expect(res.stroke).toBe("#7c3aed");
    expect(res.style.color).toBe("#7c3aed");
    expect(res.style.stroke).toBe("#7c3aed");
  });

  it("returns matching color, stroke, and style properties for valid agent ID", () => {
    const res = agentIconStyle("agent-123");
    const expectedColor = agentColor("agent-123");
    expect(res.color).toBe(expectedColor);
    expect(res.stroke).toBe(expectedColor);
    expect(res.style.color).toBe(expectedColor);
    expect(res.style.stroke).toBe(expectedColor);
  });

  it("respects colorMap overrides when provided", () => {
    const colorMap = new Map([["agent-123", "#00ff00"]]);
    const res = agentIconStyle("agent-123", colorMap);
    expect(res.color).toBe("#00ff00");
    expect(res.stroke).toBe("#00ff00");
    expect(res.style.color).toBe("#00ff00");
    expect(res.style.stroke).toBe("#00ff00");
  });
});

describe("filterGraphEdges", () => {
  const sampleEdges = [
    { source: "t1", target: "c1", relation: "generated" },
    { source: "t1", target: "t2", relation: "delegation" },
    { source: "c1", target: "t2", relation: "used" },
  ];

  it("returns all edges when showDelegation is true", () => {
    const res = filterGraphEdges(sampleEdges, { showDelegation: true });
    expect(res).toHaveLength(3);
    expect(res.map((e) => e.relation)).toContain("delegation");
  });

  it("filters out delegation edges when showDelegation is false", () => {
    const res = filterGraphEdges(sampleEdges, { showDelegation: false });
    expect(res).toHaveLength(2);
    expect(res.map((e) => e.relation)).not.toContain("delegation");
  });
});




