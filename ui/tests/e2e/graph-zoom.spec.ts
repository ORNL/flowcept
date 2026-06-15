/**
 * E2E tests for mouse-wheel zoom in the workflow graph visualizations.
 *
 * All three graph types rendered in the "Graphs" tab of the workflow detail
 * page use @xyflow/react. These tests verify that scroll-up zooms in and
 * scroll-down zooms out for each type — without relying on manual inspection.
 *
 * No backend needed: all API calls are intercepted and mocked via page.route().
 */

import { test, expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const WF_ID = "e2e-test-workflow";

const WORKFLOW = {
  workflow_id: WF_ID,
  name: "E2E Zoom Test Workflow",
  utc_timestamp: 1_700_000_000,
};

const TASK_SUMMARY = {
  status_counts: { FINISHED: 2 },
  activity_stats: [
    { activity_id: "step_a", count: 1, avg_duration: 5.0, min_duration: 4.0, max_duration: 6.0, status_counts: { FINISHED: 1 } },
    { activity_id: "step_b", count: 1, avg_duration: 3.0, min_duration: 2.5, max_duration: 3.5, status_counts: { FINISHED: 1 } },
  ],
  time_range: { min_started_at: 1_700_000_000, max_ended_at: 1_700_000_010 },
};

const TASKS = {
  items: [
    {
      task_id: "t1",
      activity_id: "step_a",
      status: "FINISHED",
      workflow_id: WF_ID,
      started_at: 1_700_000_000,
      ended_at: 1_700_000_005,
    },
    {
      task_id: "t2",
      activity_id: "step_b",
      status: "FINISHED",
      workflow_id: WF_ID,
      started_at: 1_700_000_005,
      ended_at: 1_700_000_008,
      used: { inputs: { data: [[1, 2], [3, 4]] } },
    },
  ],
  count: 2,
};

const DATAFLOW = {
  level: "coarse",
  nodes: [
    { id: "task:t1", kind: "task", label: "step_a", stats: {} },
    { id: "chunk:0", kind: "chunk", label: "chunk:0", stats: {} },
    { id: "task:t2", kind: "task", label: "step_b", stats: {} },
  ],
  edges: [
    { source: "task:t1", target: "chunk:0", relation: "generated" },
    { source: "chunk:0", target: "task:t2", relation: "used" },
  ],
  truncated: false,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Register mock responses for all endpoints the workflow detail page calls.
 *
 * IMPORTANT: Playwright evaluates routes LIFO (last registered = highest priority).
 * Register the catch-all FIRST (lowest priority) and specific routes LAST (highest
 * priority), so specific mocks always win over the catch-all.
 */
async function mockWorkflowApis(page: Page) {
  // Catch-all first → lowest priority; returns 404 fast so missing mocks fail
  // immediately instead of hanging waiting for a backend that isn't running.
  await page.route("**/api/v1/**", (route) =>
    route.fulfill({ status: 404, json: { detail: "not mocked" } }),
  );
  // Specific routes registered after → higher priority (checked before catch-all).
  await page.route("**/api/v1/info", (route) =>
    route.fulfill({ json: { service: "flowcept", version: "test" } }),
  );
  await page.route(`**/api/v1/stats/tasks/summary**`, (route) =>
    route.fulfill({ json: TASK_SUMMARY }),
  );
  await page.route(`**/api/v1/tasks/query`, (route) =>
    route.fulfill({ json: TASKS }),
  );
  // Dataflow must be registered before the workflow route so that
  // /workflows/{id}/dataflow is not swallowed by the shorter /workflows/{id} pattern.
  await page.route(`**/api/v1/workflows/${WF_ID}/dataflow`, (route) =>
    route.fulfill({ json: DATAFLOW }),
  );
  await page.route(`**/api/v1/workflows/${WF_ID}`, (route) =>
    route.fulfill({ json: WORKFLOW }),
  );
}

/**
 * Read the current zoom (scale) of the ReactFlow viewport element.
 * ReactFlow sets an inline transform like "translate(Xpx, Ypx) scale(Z)" on
 * .react-flow__viewport. DOMMatrix parses both inline and computed forms.
 */
async function getViewportScale(page: Page): Promise<number> {
  return page.locator(".react-flow__viewport").evaluate((el) => {
    const t = (el as HTMLElement).style.transform || window.getComputedStyle(el).transform;
    if (!t || t === "none") return 1;
    return new DOMMatrix(t).a; // 'a' is the x-scale component
  });
}

/**
 * Scroll-wheel over the centre of the ReactFlow canvas.
 * Negative deltaY = scroll up = zoom in; positive = zoom out.
 */
async function wheelOnCanvas(page: Page, deltaY: number, times = 5) {
  const canvas = page.locator(".react-flow");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("ReactFlow canvas not found");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  for (let i = 0; i < times; i++) {
    await page.mouse.wheel(0, deltaY);
  }
  // Allow React state + DOM paint to settle.
  await page.waitForTimeout(300);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("graph zoom — Provenance Graph (DataflowView)", () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkflowApis(page);
    await page.goto(`/workflows/${WF_ID}?tab=graph`);
    // Switch to Provenance Graph view.
    await page.getByRole("button", { name: "Provenance Graph" }).click();
    await page.locator(".react-flow__viewport").waitFor({ state: "visible" });
    // Let fitView animation finish (100ms delay + 250ms duration in FitViewHelper).
    await page.waitForTimeout(400);
  });

  test("scroll up zooms in (scale increases)", async ({ page }) => {
    // Zoom out first to ensure we are well below the maxZoom ceiling.
    await wheelOnCanvas(page, 120, 5);
    const before = await getViewportScale(page);
    await wheelOnCanvas(page, -120);
    const after = await getViewportScale(page);
    expect(after).toBeGreaterThan(before);
  });

  test("scroll down zooms out (scale decreases)", async ({ page }) => {
    // First zoom in so there is room to zoom out.
    await wheelOnCanvas(page, -120, 5);
    const before = await getViewportScale(page);
    await wheelOnCanvas(page, 120, 8);
    const after = await getViewportScale(page);
    expect(after).toBeLessThan(before);
  });
});

test.describe("graph zoom — Activity Graph (DagView activity mode)", () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkflowApis(page);
    // Default graph type is "Activity Graph".
    await page.goto(`/workflows/${WF_ID}?tab=graph`);
    await page.locator(".react-flow__viewport").waitFor({ state: "visible" });
    // Let fitView animation finish (100ms delay + 250ms duration in FitViewHelper).
    await page.waitForTimeout(400);
  });

  test("scroll up zooms in", async ({ page }) => {
    // Zoom out first to ensure we are well below the maxZoom ceiling.
    await wheelOnCanvas(page, 120, 5);
    const before = await getViewportScale(page);
    await wheelOnCanvas(page, -120);
    const after = await getViewportScale(page);
    expect(after).toBeGreaterThan(before);
  });

  test("scroll down zooms out", async ({ page }) => {
    await wheelOnCanvas(page, -120, 5);
    const before = await getViewportScale(page);
    await wheelOnCanvas(page, 120, 8);
    const after = await getViewportScale(page);
    expect(after).toBeLessThan(before);
  });
});

test.describe("graph zoom — Task Graph (DagView task mode)", () => {
  test.beforeEach(async ({ page }) => {
    await mockWorkflowApis(page);
    await page.goto(`/workflows/${WF_ID}?tab=graph`);
    await page.getByRole("button", { name: "Task Graph" }).click();
    await page.locator(".react-flow__viewport").waitFor({ state: "visible" });
    // Let fitView animation finish (100ms delay + 250ms duration in FitViewHelper).
    await page.waitForTimeout(400);
  });

  test("scroll up zooms in", async ({ page }) => {
    // Zoom out first to ensure we are well below the maxZoom ceiling.
    await wheelOnCanvas(page, 120, 5);
    const before = await getViewportScale(page);
    await wheelOnCanvas(page, -120);
    const after = await getViewportScale(page);
    expect(after).toBeGreaterThan(before);
  });

  test("scroll down zooms out", async ({ page }) => {
    await wheelOnCanvas(page, -120, 5);
    const before = await getViewportScale(page);
    await wheelOnCanvas(page, 120, 8);
    const after = await getViewportScale(page);
    expect(after).toBeLessThan(before);
  });
});

test.describe("graph type buttons — naming", () => {
  test("dataflow graph button is labelled 'Provenance Graph'", async ({ page }) => {
    await mockWorkflowApis(page);
    await page.goto(`/workflows/${WF_ID}?tab=graph`);
    await expect(page.getByRole("button", { name: "Provenance Graph" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Dataflow Graph" })).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// Agent icon colors in DAG graph nodes
// ---------------------------------------------------------------------------

const TASKS_WITH_TWO_AGENTS = {
  items: [
    {
      task_id: "ta1",
      activity_id: "orchestrate",
      status: "FINISHED",
      workflow_id: WF_ID,
      started_at: 1_700_000_000,
      ended_at: 1_700_000_005,
      agent_id: "orchestrator_agent_aaaabbbb-1111-2222-3333-444455556666",
    },
    {
      task_id: "ta2",
      activity_id: "compute",
      status: "FINISHED",
      workflow_id: WF_ID,
      started_at: 1_700_000_005,
      ended_at: 1_700_000_010,
      agent_id: "hpc_agent_ccccdddd-5555-6666-7777-888899990000",
    },
  ],
  count: 2,
};

const TASK_SUMMARY_TWO_AGENTS = {
  status_counts: { FINISHED: 2 },
  activity_stats: [
    { activity_id: "orchestrate", count: 1, avg_duration: 5.0, min_duration: 5.0, max_duration: 5.0, status_counts: { FINISHED: 1 } },
    { activity_id: "compute", count: 1, avg_duration: 5.0, min_duration: 5.0, max_duration: 5.0, status_counts: { FINISHED: 1 } },
  ],
  time_range: { min_started_at: 1_700_000_000, max_ended_at: 1_700_000_010 },
};

test.describe("agent icon colors in DAG graph", () => {
  test("two activities with different agent types get different icon colors", async ({ page }) => {
    // Mock with tasks that have two different agent IDs
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({ status: 404, json: { detail: "not mocked" } }),
    );
    await page.route("**/api/v1/info", (route) =>
      route.fulfill({ json: { service: "flowcept", version: "test" } }),
    );
    await page.route(`**/api/v1/stats/tasks/summary**`, (route) =>
      route.fulfill({ json: TASK_SUMMARY_TWO_AGENTS }),
    );
    await page.route(`**/api/v1/tasks/query`, (route) =>
      route.fulfill({ json: TASKS_WITH_TWO_AGENTS }),
    );
    await page.route(`**/api/v1/workflows/${WF_ID}/dataflow`, (route) =>
      route.fulfill({ json: { level: "coarse", nodes: [], edges: [], truncated: false } }),
    );
    await page.route(`**/api/v1/workflows/${WF_ID}`, (route) =>
      route.fulfill({ json: WORKFLOW }),
    );

    await page.goto(`/workflows/${WF_ID}?tab=graph`);
    await page.locator(".react-flow__viewport").waitFor({ state: "visible" });
    await page.waitForTimeout(400);

    // Find agent icons in DAG nodes
    const icons = page.locator("[data-testid='dag-agent-icon']");
    await expect(icons).toHaveCount(2);

    const colors = await page.evaluate(() => {
      const els = document.querySelectorAll("[data-testid='dag-agent-icon']");
      return Array.from(els).map((el) => {
        const svg = el as SVGElement;
        return svg.style.color || svg.getAttribute("stroke") || svg.style.stroke || "";
      });
    });

    expect(colors[0]).not.toBe("");
    expect(colors[1]).not.toBe("");
    // Different agent types must get different colors
    expect(colors[0]).not.toBe(colors[1]);
  });
});
