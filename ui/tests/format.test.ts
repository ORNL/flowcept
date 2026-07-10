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
  buildAgentNameColorMap,
  applyNodePositions,
  getWorkflowTimestamp,
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

  it("sorts workflows by started_at when utc_timestamp is missing", () => {
    const workflows = [
      { workflow_id: "wf-old", name: "old run", utc_timestamp: 1_700_000_000 },
      { workflow_id: "wf-new", name: "new run", started_at: 1_780_000_000 },
    ];
    const sorted = sortWorkflows(workflows);
    expect(getWorkflowTimestamp(sorted[0])).toBe(1_780_000_000);
    expect(sorted[0].workflow_id).toBe("wf-new");
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

  it("returns a color string for valid agent IDs", () => {
    const color = agentColor("agent-1");
    // hsl(...) OR #hex — just must be a non-empty string
    expect(typeof color).toBe("string");
    expect(color.length).toBeGreaterThan(0);
  });

  it("returns deterministic color for the same agent ID", () => {
    expect(agentColor("agent-1")).toBe(agentColor("agent-1"));
  });

  it("circulates across multiple colors for different IDs", () => {
    const colors = new Set<string>();
    for (let i = 0; i < 50; i++) {
      colors.add(agentColor(`agent-${i}`));
    }
    expect(colors.size).toBeGreaterThan(5);
  });

  it("does not collide for 'Orchestrator' and 'HPCAgent' (regression: both mapped to palette[6] with mod-16 hash)", () => {
    expect(agentColor(undefined, "Orchestrator")).not.toBe(agentColor(undefined, "HPCAgent"));
  });

  it("same name always produces the same color; different names produce different colors", () => {
    // Same name → deterministic: identity doesn't matter, name drives the color.
    expect(agentColor(undefined, "my_agent")).toBe(agentColor(undefined, "my_agent"));
    // Different names → distinct colors.
    expect(agentColor(undefined, "agent_alpha")).not.toBe(agentColor(undefined, "agent_beta"));
    expect(agentColor(undefined, "agent_beta")).not.toBe(agentColor(undefined, "agent_gamma"));
    expect(agentColor(undefined, "agent_alpha")).not.toBe(agentColor(undefined, "agent_gamma"));
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

// ---------------------------------------------------------------------------
// buildAgentNameColorMap
// ---------------------------------------------------------------------------

describe("buildAgentNameColorMap", () => {
  it("returns an empty map for an empty input", () => {
    expect(buildAgentNameColorMap([]).size).toBe(0);
  });

  it("assigns distinct colors to agents with different names", () => {
    const map = buildAgentNameColorMap([
      "orchestrator_agent_0434e054-3301-4439-b1f0-4a8f000b9b56",
      "hpc_agent_a2696d28-c359-4fa6-bdf9-e04c5589e689",
    ]);
    expect(map.size).toBe(2);
    const colors = Array.from(map.values());
    expect(colors[0]).not.toBe(colors[1]);
  });

  it("assigns the SAME color to two IDs that share a name (same agent type)", () => {
    // Two different orchestrator UUIDs — both have name "orchestrator_agent"
    const map = buildAgentNameColorMap([
      "orchestrator_agent_0434e054-3301-4439-b1f0-4a8f000b9b56",
      "orchestrator_agent_deadbeef-1234-5678-abcd-ef0123456789",
    ]);
    // Only one unique name → one entry in the map
    expect(map.size).toBe(1);
    expect(map.has("orchestrator_agent")).toBe(true);
  });

  it("keys are agent names, not raw IDs", () => {
    const map = buildAgentNameColorMap([
      "orchestrator_agent_0434e054-3301-4439-b1f0-4a8f000b9b56",
      "hpc_agent_a2696d28-c359-4fa6-bdf9-e04c5589e689",
    ]);
    expect(map.has("orchestrator_agent")).toBe(true);
    expect(map.has("hpc_agent")).toBe(true);
  });

  it("skips null/undefined entries", () => {
    const map = buildAgentNameColorMap([null, undefined, "hpc_agent_a2696d28-c359-4fa6-bdf9-e04c5589e689"]);
    expect(map.size).toBe(1);
  });

  it("returns a non-empty color string (hsl or hex)", () => {
    const map = buildAgentNameColorMap(["orchestrator_agent_0434e054-3301-4439-b1f0-4a8f000b9b56"]);
    const color = Array.from(map.values())[0];
    expect(typeof color).toBe("string");
    expect(color.length).toBeGreaterThan(0);
  });

  it("is cross-view consistent: same agent name maps to same color regardless of which peers are present", () => {
    // Simulates agents list (3 agents) vs workflow graph (2 agents — hpc_agent absent)
    const fullMap = buildAgentNameColorMap([
      "orchestrator_agent_aaaabbbb-1111-2222-3333-444455556666",
      "hpc_agent_ccccdddd-5555-6666-7777-888899990000",
      "data_worker_eeeeffff-9999-0000-aaaa-bbbbccccdddd",
    ]);
    const graphMap = buildAgentNameColorMap([
      "orchestrator_agent_aaaabbbb-1111-2222-3333-444455556666",
      "data_worker_eeeeffff-9999-0000-aaaa-bbbbccccdddd",
    ]);
    expect(fullMap.get("orchestrator_agent")).toBe(graphMap.get("orchestrator_agent"));
    expect(fullMap.get("data_worker")).toBe(graphMap.get("data_worker"));
  });
});

// ---------------------------------------------------------------------------
// agentIconStyle — name-based colorMap lookup
// ---------------------------------------------------------------------------

describe("agentIconStyle with name-based colorMap", () => {
  it("resolves color by agent name when colorMap is keyed by name", () => {
    // colorMap keyed by name, not raw ID
    const colorMap = new Map([["orchestrator_agent", "#ff0000"]]);
    const res = agentIconStyle("orchestrator_agent_0434e054-3301-4439-b1f0-4a8f000b9b56", colorMap);
    expect(res.color).toBe("#ff0000");
    expect(res.stroke).toBe("#ff0000");
  });

  it("two IDs with the same name resolve to the same color from the map", () => {
    const colorMap = new Map([["orchestrator_agent", "#abcdef"]]);
    // Both share the "orchestrator_agent" prefix; UUID suffixes are stripped by getAgentNameFromId
    const r1 = agentIconStyle("orchestrator_agent_0434e054-3301-4439-b1f0-4a8f000b9b56", colorMap);
    const r2 = agentIconStyle("orchestrator_agent_deadbeef-1234-5678-abcd-ef0123456789", colorMap);
    expect(r1.color).toBe("#abcdef");
    expect(r2.color).toBe("#abcdef");
  });

  it("falls back to agentColor when the name is not in the map", () => {
    const colorMap = new Map([["other_agent", "#123456"]]);
    const res = agentIconStyle("orchestrator_agent_0434e054-3301-4439-b1f0-4a8f000b9b56", colorMap);
    // not in map → falls back to deterministic agentColor
    expect(res.color).toBe(agentColor("orchestrator_agent_0434e054-3301-4439-b1f0-4a8f000b9b56"));
  });
});

// ---------------------------------------------------------------------------
// Cross-format consistency: plain-UUID vs named-UUID agent IDs
// ---------------------------------------------------------------------------

describe("agentIconStyle — same name, different ID formats", () => {
  it("plain-UUID agent ID and named-UUID agent ID with same name get identical color when name is passed", () => {
    // Real scenario: "000bfd8d-..." (plain UUID, no name in ID) and "hpc_agent_c8ce2b3a-..." both have name "HPCAgent"
    const plainUUID = "000bfd8d-8c3c-4510-b8bd-939f2a5dfa1c";
    const namedUUID = "hpc_agent_c8ce2b3a-1fdc-4bd4-90d4-6287e0860ad3";
    const c1 = agentIconStyle(plainUUID, undefined, "HPCAgent").color;
    const c2 = agentIconStyle(namedUUID, undefined, "HPCAgent").color;
    expect(c1).toBe(c2);
  });

  it("two different named-UUID agents with different names get different colors even without explicit name", () => {
    // DagView scenario: extracts name from agent_id using getAgentNameFromId
    const orch = "orchestrator_agent_aaaabbbb-1111-2222-3333-444455556666";
    const hpc = "hpc_agent_ccccdddd-5555-6666-7777-888899990000";
    expect(agentColor(orch)).not.toBe(agentColor(hpc));
  });

  it("agents list scenario: building colorMap from agent names gives consistent lookup", () => {
    // Simulates agents.index.tsx: agents have both agent_id (different formats) and name
    // colorMap must be keyed by name so agentIconStyle(id, map, name) always finds the right color
    const agents = [
      { agent_id: "000bfd8d-8c3c-4510-b8bd-939f2a5dfa1c", name: "HPCAgent" },
      { agent_id: "hpc_agent_c8ce2b3a-1fdc-4bd4-90d4-6287e0860ad3", name: "HPCAgent" },
      { agent_id: "0f3b8dab-1765-4347-8e85-88d2c35c56be", name: "Orchestrator" },
      { agent_id: "orchestrator_agent_b81e76aa-cb21-4a83-a07c-7327aca97ab0", name: "Orchestrator" },
    ];
    // Build color map keyed by name (not by extracted ID)
    const colorMap = new Map(agents.map((a) => [a.name, agentColor(undefined, a.name)]));
    // All HPCAgent instances must resolve to the same color
    const colors = agents.map((a) => agentIconStyle(a.agent_id, colorMap, a.name).color);
    expect(colors[0]).toBe(colors[1]); // both HPCAgent
    expect(colors[2]).toBe(colors[3]); // both Orchestrator
    // Different agent types must differ
    expect(colors[0]).not.toBe(colors[2]);
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



