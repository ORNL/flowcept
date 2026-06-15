/**
 * E2E tests: Agents list → Agent detail page.
 *
 * Covers:
 *  1. Agents list shows agent cards that are clickable links to the detail page.
 *  2. Agent detail page renders four tabs: tasks, telemetry, dashboard, raw.
 *  3. Tasks tab shows the agent's tasks; clicking a row opens the TaskDrawer.
 *  4. Activity column cells are clickable and filter the task list.
 *  5. Raw tab renders the agent JSON.
 *  6. Workflow detail page: activity_id column is clickable and sets the activity filter.
 *
 * All API calls are intercepted. No backend required.
 * Playwright evaluates routes LIFO — register catch-all FIRST, specific routes LAST.
 */

import { test, expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const AGENT_ID = "e2e-test-agent-001";
const AGENT_ID_2 = "orchestrator_agent_aaaabbbb-1111-2222-3333-444455556666";
const AGENT_ID_3 = "orchestrator_agent_ccccdddd-5555-6666-7777-888899990000";

const AGENTS_LIST = {
  items: [
    {
      agent_id: AGENT_ID,
      name: "Test Agent",
      task_count: 3,
      activities: ["step_a", "step_b"],
      source_agent_ids: [AGENT_ID_2],
      campaign_ids: ["camp-1"],
      workflow_ids: ["wf-001", "wf-002"],
      last_active: 1_700_000_020,
      registered_at: 1_700_000_000,
    },
    {
      agent_id: AGENT_ID_2,
      name: "Orchestrator",
      task_count: 2,
      activities: ["plan"],
      source_agent_ids: [],
      campaign_ids: ["camp-1"],
      workflow_ids: ["wf-001"],
      last_active: 1_700_000_010,
      registered_at: 1_700_000_001,
    },
    {
      agent_id: AGENT_ID_3,
      name: "Orchestrator",
      task_count: 1,
      activities: ["plan"],
      source_agent_ids: [],
      campaign_ids: ["camp-2"],
      workflow_ids: ["wf-002"],
      last_active: 1_700_000_005,
      registered_at: 1_700_000_002,
    },
  ],
  count: 3,
};

const AGENT_DETAIL = {
  agent: { ...AGENTS_LIST.items[0], source_agent_ids: [AGENT_ID_2] },
  task_summary: {
    status_counts: { FINISHED: 3 },
    activity_stats: [
      { activity_id: "step_a", count: 2, avg_duration: 5.0, min_duration: 4.0, max_duration: 6.0, status_counts: { FINISHED: 2 } },
      { activity_id: "step_b", count: 1, avg_duration: 3.0, min_duration: 3.0, max_duration: 3.0, status_counts: { FINISHED: 1 } },
    ],
    time_range: { min_started_at: 1_700_000_000, max_ended_at: 1_700_000_020 },
  },
};

const AGENT_TASKS = {
  items: [
    {
      task_id: "task-a1",
      activity_id: "step_a",
      status: "FINISHED",
      agent_id: AGENT_ID,
      workflow_id: "wf-001",
      started_at: 1_700_000_000,
      ended_at: 1_700_000_005,
    },
    {
      task_id: "task-a2",
      activity_id: "step_a",
      status: "FINISHED",
      agent_id: AGENT_ID,
      workflow_id: "wf-001",
      started_at: 1_700_000_005,
      ended_at: 1_700_000_010,
    },
    {
      task_id: "task-b1",
      activity_id: "step_b",
      status: "FINISHED",
      agent_id: AGENT_ID,
      workflow_id: "wf-001",
      started_at: 1_700_000_010,
      ended_at: 1_700_000_013,
    },
  ],
  count: 3,
};

const CAMPAIGN_ID = "campaign-test-001";

// Dataflow graph with two "train" tasks that share activity_id, so they collapse
// into one coarse super-node with count=2 in the Coarse Provenance Graph view.
const COARSE_DATAFLOW = {
  level: "coarse",
  truncated: false,
  nodes: [
    { id: "task:t1", kind: "task", label: "train", stats: { activity_id: "train", started_at: 0, ended_at: 5 } },
    { id: "task:t2", kind: "task", label: "train", stats: { activity_id: "train", started_at: 10, ended_at: 20 } },
    { id: "task:t3", kind: "task", label: "eval",  stats: { activity_id: "eval",  started_at: 25, ended_at: 28 } },
    { id: "chunk:c1", kind: "chunk", label: "loss", stats: {} },
    { id: "chunk:c2", kind: "chunk", label: "loss", stats: {} },
  ],
  edges: [
    { source: "task:t1", target: "chunk:c1", relation: "generated" },
    { source: "task:t2", target: "chunk:c2", relation: "generated" },
    { source: "chunk:c1", target: "task:t3", relation: "used" },
    { source: "chunk:c2", target: "task:t3", relation: "used" },
  ],
};

const TIMESERIES_ROWS = [
  {
    started_at: 1_700_000_000,
    task_id: "task-a1",
    activity_id: "step_a",
    "telemetry_at_end.cpu.percent_all": 25.0,
    "telemetry_at_end.memory.virtual.used": 7_586_103_296,
    "telemetry_at_end.process.cpu_percent": 0.5,
    "telemetry_at_end.process.memory_percent": 1.2,
    "telemetry_at_end.disk.io.read_bytes": 0,
    "telemetry_at_end.network.netio.bytes_sent": 1024,
  },
  {
    started_at: 1_700_000_005,
    task_id: "task-a2",
    activity_id: "step_a",
    "telemetry_at_end.cpu.percent_all": 30.0,
    "telemetry_at_end.memory.virtual.used": 7_600_000_000,
    "telemetry_at_end.process.cpu_percent": 0.8,
    "telemetry_at_end.process.memory_percent": 1.3,
    "telemetry_at_end.disk.io.read_bytes": 512,
    "telemetry_at_end.network.netio.bytes_sent": 2048,
  },
];

const TASK_DETAIL = {
  ...AGENT_TASKS.items[0],
  source_agent_id: AGENT_ID_2,
  campaign_id: CAMPAIGN_ID,
  submitted_at: 1_699_999_995,
  registered_at: 1_699_999_998,
};

const WF_ID = "wf-001";
const WORKFLOW = {
  workflow_id: WF_ID,
  name: "Activity Click Test Workflow",
  utc_timestamp: 1_700_000_000,
  campaign_id: CAMPAIGN_ID,
};
const WORKFLOW_TASKS = {
  items: [
    { task_id: "wt1", activity_id: "step_x", status: "FINISHED", workflow_id: WF_ID, started_at: 1_700_000_000, ended_at: 1_700_000_003 },
    { task_id: "wt2", activity_id: "step_y", status: "FINISHED", workflow_id: WF_ID, started_at: 1_700_000_003, ended_at: 1_700_000_006 },
  ],
  count: 2,
};
const WORKFLOW_SUMMARY = {
  status_counts: { FINISHED: 2 },
  activity_stats: [
    { activity_id: "step_x", count: 1, avg_duration: 3.0, min_duration: 3.0, max_duration: 3.0, status_counts: { FINISHED: 1 } },
    { activity_id: "step_y", count: 1, avg_duration: 3.0, min_duration: 3.0, max_duration: 3.0, status_counts: { FINISHED: 1 } },
  ],
  time_range: { min_started_at: 1_700_000_000, max_ended_at: 1_700_000_006 },
};

// ---------------------------------------------------------------------------
// Mock helpers
// ---------------------------------------------------------------------------

async function mockAgentListApis(page: Page) {
  await page.route("**/api/v1/**", (route) =>
    route.fulfill({ status: 404, json: { detail: "not mocked" } }),
  );
  await page.route("**/api/v1/info", (route) =>
    route.fulfill({ json: { service: "flowcept", version: "test" } }),
  );
  await page.route("**/api/v1/agents", (route) =>
    route.fulfill({ json: AGENTS_LIST }),
  );
}

async function mockAgentDetailApis(page: Page) {
  await page.route("**/api/v1/**", (route) =>
    route.fulfill({ status: 404, json: { detail: "not mocked" } }),
  );
  await page.route("**/api/v1/info", (route) =>
    route.fulfill({ json: { service: "flowcept", version: "test" } }),
  );
  await page.route("**/api/v1/stats/tasks/summary**", (route) =>
    route.fulfill({ json: AGENT_DETAIL.task_summary }),
  );
  await page.route("**/api/v1/tasks/query", (route) =>
    route.fulfill({ json: AGENT_TASKS }),
  );
  await page.route(`**/api/v1/agents/${AGENT_ID}`, (route) =>
    route.fulfill({ json: AGENT_DETAIL }),
  );
  await page.route("**/api/v1/agents", (route) =>
    route.fulfill({ json: AGENTS_LIST }),
  );
  await page.route(`**/api/v1/tasks/${TASK_DETAIL.task_id}`, (route) =>
    route.fulfill({ json: TASK_DETAIL }),
  );
}

async function mockWorkflowDetailApis(page: Page) {
  await page.route("**/api/v1/**", (route) =>
    route.fulfill({ status: 404, json: { detail: "not mocked" } }),
  );
  await page.route("**/api/v1/info", (route) =>
    route.fulfill({ json: { service: "flowcept", version: "test" } }),
  );
  await page.route("**/api/v1/stats/tasks/summary**", (route) =>
    route.fulfill({ json: WORKFLOW_SUMMARY }),
  );
  await page.route("**/api/v1/tasks/query", (route) =>
    route.fulfill({ json: WORKFLOW_TASKS }),
  );
  await page.route(`**/api/v1/workflows/${WF_ID}`, (route) =>
    route.fulfill({ json: WORKFLOW }),
  );
  // Agents list: items 0 and 1 have wf-001 in workflow_ids (used by Agents tab)
  await page.route("**/api/v1/agents", (route) =>
    route.fulfill({ json: AGENTS_LIST }),
  );
}

// ---------------------------------------------------------------------------
// Tests: Agents list
// ---------------------------------------------------------------------------

test.describe("Agents list", () => {
  test("shows agent cards and clicking navigates to detail page", async ({ page }) => {
    await mockAgentListApis(page);
    await mockAgentDetailApis(page);
    await page.goto("/agents");

    // The agent card should appear.
    await expect(page.getByText("Test Agent")).toBeVisible();

    // Click the card — should navigate to /agents/<id>.
    await page.getByText("Test Agent").click();
    await expect(page).toHaveURL(new RegExp(`/agents/${AGENT_ID}`));
  });

  test("agent card shows workflow ids", async ({ page }) => {
    await mockAgentListApis(page);
    await page.goto("/agents");
    await expect(page.getByText("wf-001").first()).toBeVisible();
  });

  test("agent card shows source agents as links labelled 'source agents:'", async ({ page }) => {
    await mockAgentListApis(page);
    await page.goto("/agents");
    // The label must say "source agents:" not "sources:"
    await expect(page.getByText(/source agents:/i)).toBeVisible();
    // Each source agent id must be a clickable link to its agent page (monospace inline link)
    const link = page.locator(`a.text-accent[href$="${AGENT_ID_2}"]`);
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", `/agents/${AGENT_ID_2}`);
  });

  test("activity names in agent list cards are displayed but clicking them does NOT navigate to a new page", async ({ page }) => {
    await mockAgentListApis(page);
    await page.goto("/agents");
    await expect(page.getByText("Test Agent")).toBeVisible();

    // AGENTS_LIST.items[0] has activities: ["step_a", "step_b"]
    // Activities must be visible as text — NOT as <a> links that navigate away.
    await expect(page.getByText("step_a")).toBeVisible({ timeout: 5_000 });

    // There must be NO <a href> pointing to an activity-filtered agent detail URL
    // (that would navigate the user away from the list page).
    const actNavLink = page.locator(`a[href*="activity=step_a"]`);
    await expect(actNavLink).toHaveCount(0, { timeout: 2_000 });
  });

  test("two agents with the same name get the same icon color; different names get different colors", async ({ page }) => {
    await mockAgentListApis(page);
    await page.goto("/agents");

    // Wait for all three cards to render
    await expect(page.getByText("Test Agent")).toBeVisible();
    await expect(page.getByText("Orchestrator").first()).toBeVisible();

    // Grab stroke color of each Bot icon (first SVG path inside each card header)
    const colors = await page.evaluate(() => {
      const svgs = document.querySelectorAll("[data-testid='agent-icon']");
      return Array.from(svgs).map((svg) => (svg as SVGElement).style.color || (svg as SVGElement).getAttribute("color") || "");
    });

    expect(colors).toHaveLength(3);
    // The two Orchestrator cards (index 1 and 2) must share the same color
    expect(colors[1]).toBe(colors[2]);
    // Test Agent (index 0) must differ from Orchestrator
    expect(colors[0]).not.toBe(colors[1]);
  });
});

// ---------------------------------------------------------------------------
// Tests: Agent detail page
// ---------------------------------------------------------------------------

test.describe("Agent detail page", () => {
  test.beforeEach(async ({ page }) => {
    await mockAgentDetailApis(page);
    await page.goto(`/agents/${AGENT_ID}`);
  });

  test("shows agent name and id in header", async ({ page }) => {
    await expect(page.getByText("Test Agent")).toBeVisible();
    await expect(page.getByText(AGENT_ID)).toBeVisible();
  });

  test("renders four tabs: tasks, telemetry, dashboard, raw", async ({ page }) => {
    for (const tab of ["tasks", "telemetry", "dashboard", "raw"]) {
      await expect(page.getByRole("button", { name: tab, exact: true })).toBeVisible();
    }
  });

  test("tasks tab shows task rows", async ({ page }) => {
    // Activity cells are rendered as buttons in the table rows.
    await expect(page.getByRole("button", { name: "step_a", exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "step_b", exact: true }).first()).toBeVisible();
  });

  test("clicking a task row opens the TaskDrawer", async ({ page }) => {
    // Click the first task row (task-a1, activity step_a).
    const rows = page.locator("table tbody tr");
    await rows.first().click();
    // TaskDrawer should appear — it shows the task_id or activity.
    await expect(page.locator("[data-testid='task-drawer'], .task-drawer, [role='dialog']").or(
      page.getByText(TASK_DETAIL.task_id)
    )).toBeVisible({ timeout: 5_000 });
  });

  test("clicking an activity cell sets the activity filter in the URL", async ({ page }) => {
    // Click the step_b activity button (only one row has step_b).
    const activityBtn = page.getByRole("button", { name: "step_b", exact: true }).first();
    await activityBtn.click();
    // The URL should now contain activity=step_b.
    await expect(page).toHaveURL(/activity=step_b/);
  });

  test("clicking an activity cell opens the activity inspector panel with stats", async ({ page }) => {
    // Click the step_a activity button.
    const activityBtn = page.getByRole("button", { name: "step_a", exact: true }).first();
    await activityBtn.click();

    // The activity inspector panel must appear with:
    //  - the activity name as a heading
    //  - task count from activity_stats (step_a has count: 2)
    await expect(page.getByTestId("activity-drawer")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId("activity-drawer")).toContainText("step_a");
    await expect(page.getByTestId("activity-drawer")).toContainText("2");
  });

  test("only one inspector panel is open at a time — opening activity closes task drawer", async ({ page }) => {
    // First open the TaskDrawer by clicking a task row.
    await page.getByText(AGENT_TASKS.items[0].task_id, { exact: true }).click();
    // Wait for task drawer to appear.
    await page.waitForURL(/task=task-a1/, { timeout: 5_000 });

    // Now click an activity button — the TaskDrawer must close and ActivityDrawer must open.
    const activityBtn = page.getByRole("button", { name: "step_b", exact: true }).first();
    await activityBtn.click();

    await expect(page.getByTestId("activity-drawer")).toBeVisible({ timeout: 5_000 });
    // TaskDrawer must not coexist — ?task= must be cleared from the URL.
    await expect(page).not.toHaveURL(/task=/);
  });

  test("opening a task row closes the activity drawer", async ({ page }) => {
    // First open the ActivityDrawer.
    await page.getByRole("button", { name: "step_a", exact: true }).first().click();
    await expect(page.getByTestId("activity-drawer")).toBeVisible({ timeout: 5_000 });

    // Now click a task row — the ActivityDrawer must close and TaskDrawer must open.
    await page.getByText(AGENT_TASKS.items[0].task_id, { exact: true }).click();
    await page.waitForURL(/task=task-a1/, { timeout: 5_000 });

    // activity-drawer must be gone — ?activity= must be cleared from the URL.
    await expect(page).not.toHaveURL(/activity=/);
    await expect(page.getByTestId("activity-drawer")).not.toBeVisible();
  });

  test("header shows source agents as links labelled 'Source agents:'", async ({ page }) => {
    await expect(page.getByText(/source agents:/i)).toBeVisible();
    const link = page.locator(`a.text-accent[href$="${AGENT_ID_2}"]`);
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", `/agents/${AGENT_ID_2}`);
  });

  test("task drawer shows workflow, agent, source agent, campaign as links and timestamps as human-readable text", async ({ page }) => {
    // DataTable renders div rows (not <tr>). Click via the font-mono task_id span which bubbles up.
    await expect(page.getByText(TASK_DETAIL.task_id, { exact: true })).toBeVisible({ timeout: 5_000 });
    await page.getByText(TASK_DETAIL.task_id, { exact: true }).click();

    // workflow_id link → /workflows/wf-001
    const wfLink = page.locator(`a[href*="/workflows/${TASK_DETAIL.workflow_id}"]`).first();
    await expect(wfLink).toBeVisible({ timeout: 5_000 });

    // agent_id link → /agents/<agent_id>
    const agentLink = page.locator(`a[href*="/agents/${TASK_DETAIL.agent_id}"]`).first();
    await expect(agentLink).toBeVisible();

    // source_agent_id link → /agents/<source_agent_id>
    const srcLink = page.locator(`a[href*="/agents/${TASK_DETAIL.source_agent_id}"]`).first();
    await expect(srcLink).toBeVisible();

    // campaign_id link → /campaigns/<campaign_id>
    const campLink = page.locator(`a[href*="/campaigns/${TASK_DETAIL.campaign_id}"]`).first();
    await expect(campLink).toBeVisible();

    // timestamps should render as human-readable text (not raw epoch numbers)
    // fmtTs(1_700_000_000) produces something like "Nov 14, 2023" or similar
    // Just verify the raw epoch number "1700000000" is NOT directly visible in the field labels section
    const drawerCard = page.locator(".fixed.inset-y-0.right-0 .card").first();
    await expect(drawerCard).not.toContainText("1700000000");
  });

  test("telemetry tab renders ECharts canvas and metric buttons when API returns data", async ({ page }) => {
    // Register timeseries mock AFTER beforeEach (LIFO → higher priority than catch-all 404).
    // Both the "all fields" and "single field" POST calls return the same rows.
    await page.route("**/api/v1/stats/timeseries", (route) =>
      route.fulfill({ json: { rows: TIMESERIES_ROWS, count: TIMESERIES_ROWS.length } }),
    );

    await page.getByRole("button", { name: "telemetry", exact: true }).click();

    // Metric toggle buttons must appear (always rendered by TelemetryChart)
    await expect(page.getByRole("button", { name: "CPU %", exact: true }).first()).toBeVisible({ timeout: 5_000 });

    // Neither "no tasks matched" nor "no telemetry values" fallback must be shown
    await expect(page.getByText(/no tasks matched/i)).not.toBeVisible();
    await expect(page.getByText(/no telemetry values/i)).not.toBeVisible();

    // The ECharts canvas must be injected and visible
    const canvas = page.locator("canvas").first();
    await expect(canvas).toBeVisible({ timeout: 5_000 });
  });

  test("telemetry tab sends agent_id-only filter to timeseries API (no source_agent_id)", async ({ page }) => {
    // Capture the POST request bodies to verify the filter.
    // The filter MUST be { agent_id: <id> } — NOT $or with source_agent_id,
    // because telemetry is shown only for tasks directly owned by this agent.
    const capturedBodies: unknown[] = [];
    await page.route("**/api/v1/stats/timeseries", async (route) => {
      const body = route.request().postDataJSON();
      if (body) capturedBodies.push(body);
      await route.fulfill({ json: { rows: TIMESERIES_ROWS, count: TIMESERIES_ROWS.length } });
    });

    await page.getByRole("button", { name: "telemetry", exact: true }).click();
    await page.getByRole("button", { name: "CPU %", exact: true }).first().waitFor({ state: "visible", timeout: 5_000 });

    expect(capturedBodies.length).toBeGreaterThan(0);

    for (const body of capturedBodies) {
      const filter = (body as { filter: unknown }).filter as Record<string, unknown>;
      expect(filter).toBeDefined();
      expect(filter["agent_id"]).toBe(AGENT_ID);
      expect(filter["$or"]).toBeUndefined();
      expect(filter["source_agent_id"]).toBeUndefined();
    }
  });

  test("raw tab shows the agent JSON", async ({ page }) => {
    await page.getByRole("button", { name: "raw", exact: true }).click();
    // The agent_id should appear in the raw JSON tree.
    await expect(page.getByText(AGENT_ID)).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Tests: Workflow detail — activity_id is clickable
// ---------------------------------------------------------------------------

test.describe("Workflow detail — activity column", () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkflowDetailApis(page);
    await page.goto(`/workflows/${WF_ID}`);
  });

  test("clicking an activity name sets the activity filter in the URL", async ({ page }) => {
    // Activity cells are buttons; wait for the table rows to appear first.
    await expect(page.getByRole("button", { name: "step_x", exact: true }).first()).toBeVisible();

    // Click the step_x activity button in a task row.
    await page.getByRole("button", { name: "step_x", exact: true }).first().click();

    await expect(page).toHaveURL(/activity=step_x/);
  });

  test("task_id cells are styled as links (accent color) to signal they are clickable", async ({ page }) => {
    // Task IDs in the task table must be visually afforded as clickable
    // (text-accent class or equivalent), since clicking a row opens the TaskDrawer.
    const taskIdCell = page.locator(".font-mono.text-accent").first();
    await expect(taskIdCell).toBeVisible({ timeout: 5_000 });
  });

  test("workflow header shows campaign as a link and utc_timestamp as human-readable date", async ({ page }) => {
    // campaign link must point to /campaigns/<id>
    const campLink = page.locator(`a[href*="/campaigns/${CAMPAIGN_ID}"]`).first();
    await expect(campLink).toBeVisible({ timeout: 5_000 });

    // utc_timestamp 1_700_000_000 must NOT appear raw in the header area
    // It is formatted by fmtTs so should render as a date string, not the epoch number
    const header = page.locator("header");
    await expect(header).not.toContainText("1700000000");
    // The formatted timestamp should be visible somewhere (anything that isn't the epoch)
    await expect(header).toContainText("Created:");
  });

  test("clicking an activity in workflow detail opens the ActivityDrawer inspector panel", async ({ page }) => {
    // Activity cells are buttons in the task table.
    await expect(page.getByRole("button", { name: "step_x", exact: true }).first()).toBeVisible();

    await page.getByRole("button", { name: "step_x", exact: true }).first().click();

    // The activity inspector (ActivityDrawer) must appear.
    await expect(page.getByTestId("activity-drawer")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId("activity-drawer")).toContainText("step_x");
  });

  test("workflow detail has an agents tab that shows a table of agents in the workflow", async ({ page }) => {
    // The agents tab must exist in the workflow detail tab bar.
    const agentsTab = page.getByRole("button", { name: "agents", exact: true });
    await expect(agentsTab).toBeVisible({ timeout: 5_000 });

    await agentsTab.click();

    // AGENTS_LIST items 0 and 1 have wf-001 in workflow_ids: "Test Agent" and "Orchestrator".
    await expect(page.getByText("Test Agent")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Orchestrator").first()).toBeVisible();

    // Must NOT navigate away — URL stays on the workflow detail page.
    await expect(page).toHaveURL(new RegExp(`/workflows/${WF_ID}`));
  });

  test("opening activity drawer in workflow detail closes task drawer (mutual exclusion)", async ({ page }) => {
    // Wait for task rows to appear.
    await expect(page.getByText("wt1", { exact: true })).toBeVisible({ timeout: 5_000 });

    // Click task row wt1 to open TaskDrawer.
    await page.getByText("wt1", { exact: true }).click();
    await page.waitForURL(/task=wt1/, { timeout: 5_000 });

    // Now click an activity button — TaskDrawer must close, ActivityDrawer must open.
    await page.getByRole("button", { name: "step_y", exact: true }).first().click();
    await expect(page.getByTestId("activity-drawer")).toBeVisible({ timeout: 5_000 });
    await expect(page).not.toHaveURL(/task=/);
  });
});

// ---------------------------------------------------------------------------
// Agent icon color consistency
// ---------------------------------------------------------------------------

// Two HPCAgent entries: one with plain UUID id, one with named-UUID id.
// Both have name="HPCAgent" so their icons MUST share the same color.
const PLAIN_UUID_AGENT_ID = "000bfd8d-8c3c-4510-b8bd-939f2a5dfa1c";
const NAMED_UUID_AGENT_ID = "hpc_agent_c8ce2b3a-1fdc-4bd4-90d4-6287e0860ad3";
const MIXED_FORMAT_AGENTS = {
  items: [
    {
      agent_id: PLAIN_UUID_AGENT_ID,
      name: "HPCAgent",
      task_count: 2,
      activities: ["train"],
      source_agent_ids: [],
      campaign_ids: [],
      workflow_ids: [],
      last_active: 1_700_000_010,
    },
    {
      agent_id: NAMED_UUID_AGENT_ID,
      name: "HPCAgent",
      task_count: 3,
      activities: ["train"],
      source_agent_ids: [],
      campaign_ids: [],
      workflow_ids: [],
      last_active: 1_700_000_020,
    },
    {
      agent_id: "orchestrator_agent_aaaabbbb-1111-2222-3333-444455556666",
      name: "Orchestrator",
      task_count: 1,
      activities: ["submit"],
      source_agent_ids: [],
      campaign_ids: [],
      workflow_ids: [],
      last_active: 1_700_000_005,
    },
  ],
  count: 3,
};

test.describe("agents list — icon color consistency", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({ status: 404, json: { detail: "not mocked" } }),
    );
    await page.route("**/api/v1/info", (route) =>
      route.fulfill({ json: { service: "flowcept", version: "test" } }),
    );
    await page.route("**/api/v1/agents", (route) =>
      route.fulfill({ json: MIXED_FORMAT_AGENTS }),
    );
    await page.goto("/agents/");
  });

  test("two HPCAgent cards (different ID formats) have the same icon color", async ({ page }) => {
    // Wait for cards to render
    await expect(page.locator("[data-testid='agent-icon']").first()).toBeVisible({ timeout: 5_000 });
    const icons = page.locator("[data-testid='agent-icon']");
    await expect(icons).toHaveCount(3);

    const colors = await page.evaluate(() => {
      const els = document.querySelectorAll("[data-testid='agent-icon']");
      return Array.from(els).map((el) => {
        const svg = el as SVGElement;
        return svg.style.color || svg.style.stroke || svg.getAttribute("color") || "";
      });
    });

    // First two cards are both HPCAgent — must share the same icon color
    expect(colors[0]).not.toBe("");
    expect(colors[1]).not.toBe("");
    expect(colors[0]).toBe(colors[1]);

    // Orchestrator (third) must be a different color than HPCAgent
    expect(colors[2]).not.toBe(colors[0]);
  });
});

test.describe("Agent detail — header metadata", () => {
  test.beforeEach(async ({ page }) => {
    await mockAgentDetailApis(page);
    await page.goto(`/agents/${AGENT_ID}`);
  });

  test("agent header shows campaign_ids as links and registered_at in human-readable format", async ({ page }) => {
    // campaign_ids: ["camp-1"] — should render as a link to /campaigns/camp-1
    const campLink = page.locator(`a[href*="/campaigns/camp-1"]`).first();
    await expect(campLink).toBeVisible({ timeout: 5_000 });

    // registered_at 1_700_000_000 — must NOT appear as raw epoch
    const header = page.locator("header");
    await expect(header).not.toContainText("1700000000");
    // Should contain a "registered" label
    await expect(header).toContainText(/registered/i);
  });

  test("agent header shows workflow_ids as links labelled 'Workflows:'", async ({ page }) => {
    // AGENTS_LIST.items[0] has workflow_ids: ["wf-001", "wf-002"]
    const header = page.locator("header");
    await expect(header).toContainText(/workflows?:/i, { timeout: 5_000 });
    const wf1Link = page.locator(`a[href*="/workflows/wf-001"]`).first();
    await expect(wf1Link).toBeVisible();
    const wf2Link = page.locator(`a[href*="/workflows/wf-002"]`).first();
    await expect(wf2Link).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Pagination tests
// ---------------------------------------------------------------------------

const PAGE_SIZE = 30;

// 35 agents — enough to require a second page
const MANY_AGENTS = {
  items: Array.from({ length: 35 }, (_, i) => ({
    agent_id: `agent-page-${i}`,
    name: `Agent ${i}`,
    task_count: 1,
    activities: [`act_${i}`],
    source_agent_ids: [],
    campaign_ids: [],
    workflow_ids: [],
    last_active: 1_700_000_000 + i,
    registered_at: 1_700_000_000,
  })),
  count: 35,
};

// 35 workflows (each has a valid name + utc_timestamp; all present in the with_tasks mock)
const MANY_WORKFLOWS = {
  items: Array.from({ length: 35 }, (_, i) => ({
    workflow_id: `wf-page-${i}`,
    name: `Workflow ${i}`,
    utc_timestamp: 1_700_000_000 + i,
    campaign_id: "camp-1",
  })),
  count: 35,
};
// Chart data response so useWorkflowsWithTasks resolves (returns all workflow ids as rows)
const MANY_WORKFLOWS_WITH_TASKS = {
  rows: MANY_WORKFLOWS.items.map((w) => ({ workflow_id: w.workflow_id })),
  count: 35,
};

// 35 campaigns with task_count > 0
const MANY_CAMPAIGNS = {
  items: Array.from({ length: 35 }, (_, i) => ({
    campaign_id: `camp-page-${i}`,
    workflow_count: 1,
    task_count: 2,
    workflow_names: [`wf-${i}`],
    users: ["user"],
    first_ts: 1_700_000_000 + i,
    last_ts: 1_700_000_010 + i,
  })),
  count: 35,
};

async function mockManyAgentsApis(page: Page) {
  await page.route("**/api/v1/**", (route) =>
    route.fulfill({ status: 404, json: { detail: "not mocked" } }),
  );
  await page.route("**/api/v1/info", (route) =>
    route.fulfill({ json: { service: "flowcept", version: "test" } }),
  );
  await page.route("**/api/v1/agents", (route) =>
    route.fulfill({ json: MANY_AGENTS }),
  );
}

async function mockManyWorkflowsApis(page: Page) {
  await page.route("**/api/v1/**", (route) =>
    route.fulfill({ status: 404, json: { detail: "not mocked" } }),
  );
  await page.route("**/api/v1/info", (route) =>
    route.fulfill({ json: { service: "flowcept", version: "test" } }),
  );
  // Use ** suffix to match query params like ?limit=200
  await page.route("**/api/v1/workflows**", (route) =>
    route.fulfill({ json: MANY_WORKFLOWS }),
  );
  await page.route("**/api/v1/stats/chart_data", (route) =>
    route.fulfill({ json: MANY_WORKFLOWS_WITH_TASKS }),
  );
}

async function mockManyCampaignsApis(page: Page) {
  await page.route("**/api/v1/**", (route) =>
    route.fulfill({ status: 404, json: { detail: "not mocked" } }),
  );
  await page.route("**/api/v1/info", (route) =>
    route.fulfill({ json: { service: "flowcept", version: "test" } }),
  );
  await page.route("**/api/v1/campaigns", (route) =>
    route.fulfill({ json: MANY_CAMPAIGNS }),
  );
}

test.describe("Agents list — pagination", () => {
  test.beforeEach(async ({ page }) => {
    await mockManyAgentsApis(page);
    await page.goto("/agents");
    // Wait for cards to render
    await expect(page.locator(".card").first()).toBeVisible({ timeout: 5_000 });
  });

  test("shows only 30 agents on the first page when 35 exist", async ({ page }) => {
    const cards = page.locator("[data-testid='agent-icon']");
    await expect(cards).toHaveCount(PAGE_SIZE, { timeout: 5_000 });
  });

  test("shows next-page button and navigating to page 2 reveals remaining agents", async ({ page }) => {
    const nextBtn = page.getByTestId("pagination-next");
    await expect(nextBtn).toBeVisible({ timeout: 5_000 });
    await expect(nextBtn).not.toBeDisabled();

    await nextBtn.click();

    // Page 2 has 5 agents (35 total − 30 on page 1)
    const cards = page.locator("[data-testid='agent-icon']");
    await expect(cards).toHaveCount(5, { timeout: 5_000 });

    // Next button is now disabled (no page 3)
    await expect(nextBtn).toBeDisabled();
  });

  test("prev-page button is disabled on the first page", async ({ page }) => {
    const prevBtn = page.getByTestId("pagination-prev");
    await expect(prevBtn).toBeVisible({ timeout: 5_000 });
    await expect(prevBtn).toBeDisabled();
  });
});

test.describe("Workflows list — pagination", () => {
  test.beforeEach(async ({ page }) => {
    await mockManyWorkflowsApis(page);
    await page.goto("/workflows");
    // Items are sorted descending by utc_timestamp; Workflow 34 (highest ts) appears first on page 1.
    await expect(page.getByText("Workflow 34")).toBeVisible({ timeout: 5_000 });
  });

  test("shows only 30 workflows on the first page when 35 exist", async ({ page }) => {
    // Each workflow row is a flex container inside the card.
    // After sorting desc, page 1 has Workflow 34..5 (30 items), page 2 has 4..0 (5 items).
    // Workflow 0 must NOT be visible on page 1.
    await expect(page.getByText("Workflow 0")).not.toBeVisible();
    await expect(page.getByText("Workflow 5")).toBeVisible();
  });

  test("shows next-page button and navigating reveals remaining workflows", async ({ page }) => {
    const nextBtn = page.getByTestId("pagination-next");
    await expect(nextBtn).toBeVisible({ timeout: 5_000 });
    await nextBtn.click();

    // Page 2 has Workflow 4..0 (5 items). Workflow 0 should now be visible.
    await expect(page.getByText("Workflow 0")).toBeVisible({ timeout: 5_000 });
    await expect(nextBtn).toBeDisabled();
  });

  test("prev-page button is disabled on the first page", async ({ page }) => {
    const prevBtn = page.getByTestId("pagination-prev");
    await expect(prevBtn).toBeDisabled({ timeout: 5_000 });
  });
});

test.describe("Campaigns list — pagination", () => {
  test.beforeEach(async ({ page }) => {
    await mockManyCampaignsApis(page);
    await page.goto("/campaigns");
    // Items are sorted descending by last_ts; camp-page-34 (highest ts) appears first on page 1.
    await expect(page.getByText("camp-page-34").first()).toBeVisible({ timeout: 5_000 });
  });

  test("shows only 30 campaigns on the first page when 35 exist", async ({ page }) => {
    // camp-page-0 (lowest ts) is on page 2 — should NOT be visible on page 1.
    await expect(page.getByText("camp-page-0")).not.toBeVisible();
    await expect(page.getByText("camp-page-34")).toBeVisible();
  });

  test("shows next-page button and navigating reveals remaining campaigns", async ({ page }) => {
    const nextBtn = page.getByTestId("pagination-next");
    await expect(nextBtn).toBeVisible({ timeout: 5_000 });
    await nextBtn.click();

    // Page 2 has camp-page-4..0 (5 items). camp-page-0 should now be visible.
    await expect(page.getByText("camp-page-0")).toBeVisible({ timeout: 5_000 });
    await expect(nextBtn).toBeDisabled();
  });

  test("prev-page button is disabled on the first page", async ({ page }) => {
    const prevBtn = page.getByTestId("pagination-prev");
    await expect(prevBtn).toBeDisabled({ timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// Tests: Workflow detail — Provenance Graph (coarse / fine sub-toggle)
// ---------------------------------------------------------------------------

test.describe("Workflow detail — Provenance Graph", () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkflowDetailApis(page);
    // Add dataflow routes after the catch-all so they take precedence (LIFO).
    await page.route(`**/api/v1/workflows/${WF_ID}/node_positions**`, (route) =>
      route.fulfill({ json: {} }),
    );
    await page.route(`**/api/v1/workflows/${WF_ID}/dataflow**`, (route) =>
      route.fulfill({ json: COARSE_DATAFLOW }),
    );
    await page.goto(`/workflows/${WF_ID}`);
    // Navigate to the graph tab ("graph" key renders as "Graphs" in the tab bar).
    await page.getByRole("button", { name: "Graphs", exact: true }).click();
    // Click the Provenance Graph outer tab.
    await page.getByRole("button", { name: "Provenance Graph", exact: true }).click();
  });

  test("Provenance Graph tab shows coarse/fine sub-toggle", async ({ page }) => {
    await expect(page.getByRole("button", { name: "coarse", exact: true })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("button", { name: "fine", exact: true })).toBeVisible({ timeout: 5_000 });
  });

  test("coarse is the default sub-mode and renders aggregated nodes", async ({ page }) => {
    // Coarse is default — no extra click needed.
    // The two "train" task nodes collapse into one.
    await expect(
      page.locator(".react-flow__node").getByText("train", { exact: true }),
    ).toBeVisible({ timeout: 8_000 });
    await expect(page.getByText(/×2/).first()).toBeVisible({ timeout: 5_000 });
  });

  test("switching to fine sub-mode shows the full per-task graph", async ({ page }) => {
    await page.getByRole("button", { name: "fine", exact: true }).click();

    // Fine graph has 5 original nodes (t1, t2, t3, c1, c2).
    const nodes = page.locator(".react-flow__node");
    await expect(nodes.first()).toBeVisible({ timeout: 8_000 });
    const count = await nodes.count();
    expect(count).toBe(5);
  });

  test("coarse graph has fewer nodes than fine graph", async ({ page }) => {
    // Coarse: 3 nodes.
    const coarseNodes = page.locator(".react-flow__node");
    await expect(coarseNodes.first()).toBeVisible({ timeout: 8_000 });
    const coarseCount = await coarseNodes.count();
    expect(coarseCount).toBe(3);

    // Switch to fine: 5 nodes.
    await page.getByRole("button", { name: "fine", exact: true }).click();
    await expect(coarseNodes.first()).toBeVisible({ timeout: 5_000 });
    const fineCount = await coarseNodes.count();
    expect(fineCount).toBe(5);

    expect(coarseCount).toBeLessThan(fineCount);
  });
});
