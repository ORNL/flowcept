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

const AGENTS_LIST = {
  items: [
    {
      agent_id: AGENT_ID,
      name: "Test Agent",
      task_count: 3,
      activities: ["step_a", "step_b"],
      source_agent_ids: [],
      campaign_ids: ["camp-1"],
      last_active: 1_700_000_020,
      registered_at: 1_700_000_000,
    },
  ],
  count: 1,
};

const AGENT_DETAIL = {
  agent: AGENTS_LIST.items[0],
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

const TASK_DETAIL = AGENT_TASKS.items[0];

const WF_ID = "wf-001";
const WORKFLOW = {
  workflow_id: WF_ID,
  name: "Activity Click Test Workflow",
  utc_timestamp: 1_700_000_000,
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

  test("clicking an activity cell filters the task list", async ({ page }) => {
    // Click the step_b activity button (only one row has step_b).
    const activityBtn = page.getByRole("button", { name: "step_b", exact: true }).first();
    await activityBtn.click();
    // The URL should now contain activity=step_b.
    await expect(page).toHaveURL(/activity=step_b/);
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
});
