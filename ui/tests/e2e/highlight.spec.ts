/**
 * E2E tests: LLM chat → ui:highlight SSE event → DataflowView lineage dimming.
 *
 * Verifies the full path:
 *   POST /api/v1/chat → SSE "event: ui:highlight" → highlightStore.setHighlight()
 *   → DataflowView seeds BFS → lineage nodes bright, unrelated nodes dimmed (opacity 0.12)
 *
 * Graph used (two isolated chains — no shared edges):
 *   Chain A:  task:t1 → chunk:0 → task:t2
 *   Chain B:  task:t3 → chunk:1 → task:t4
 *
 * Highlight applied on task ID "t1" (raw ID, no "task:" prefix — same as what the LLM emits).
 * Expected lineage: {task:t1, chunk:0, task:t2}.  Dimmed: {task:t3, chunk:1, task:t4}.
 *
 * All API calls are intercepted via page.route(). No backend required.
 * Playwright evaluates routes LIFO — register catch-all FIRST, specific routes LAST.
 */

import { test, expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const WF_ID = "e2e-highlight-wf";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const WORKFLOW = {
  workflow_id: WF_ID,
  name: "Highlight Test Workflow",
  utc_timestamp: 1_700_000_000,
};

const TASK_SUMMARY = {
  status_counts: { FINISHED: 4 },
  activity_stats: [
    { activity_id: "step_a", count: 1, avg_duration: 5.0, min_duration: 4.0, max_duration: 6.0, status_counts: { FINISHED: 1 } },
    { activity_id: "step_b", count: 1, avg_duration: 3.0, min_duration: 2.5, max_duration: 3.5, status_counts: { FINISHED: 1 } },
    { activity_id: "step_c", count: 1, avg_duration: 2.0, min_duration: 1.5, max_duration: 2.5, status_counts: { FINISHED: 1 } },
    { activity_id: "step_d", count: 1, avg_duration: 4.0, min_duration: 3.0, max_duration: 5.0, status_counts: { FINISHED: 1 } },
  ],
  time_range: { min_started_at: 1_700_000_000, max_ended_at: 1_700_000_020 },
};

const TASKS = {
  items: [
    { task_id: "t1", activity_id: "step_a", status: "FINISHED", workflow_id: WF_ID, started_at: 1_700_000_000, ended_at: 1_700_000_005 },
    { task_id: "t2", activity_id: "step_b", status: "FINISHED", workflow_id: WF_ID, started_at: 1_700_000_005, ended_at: 1_700_000_008 },
    { task_id: "t3", activity_id: "step_c", status: "FINISHED", workflow_id: WF_ID, started_at: 1_700_000_010, ended_at: 1_700_000_015 },
    { task_id: "t4", activity_id: "step_d", status: "FINISHED", workflow_id: WF_ID, started_at: 1_700_000_015, ended_at: 1_700_000_020 },
  ],
  count: 4,
};

// Two disconnected chains — no edges cross between them.
const DATAFLOW = {
  level: "coarse",
  nodes: [
    { id: "task:t1", kind: "task", label: "step_a", stats: {} },
    { id: "chunk:0", kind: "chunk", label: "chunk:0", stats: {} },
    { id: "task:t2", kind: "task", label: "step_b", stats: {} },
    { id: "task:t3", kind: "task", label: "step_c", stats: {} },
    { id: "chunk:1", kind: "chunk", label: "chunk:1", stats: {} },
    { id: "task:t4", kind: "task", label: "step_d", stats: {} },
  ],
  edges: [
    { source: "task:t1", target: "chunk:0", relation: "generated" },
    { source: "chunk:0", target: "task:t2", relation: "used" },
    { source: "task:t3", target: "chunk:1", relation: "generated" },
    { source: "chunk:1", target: "task:t4", relation: "used" },
  ],
  truncated: false,
};

// SSE body that the mocked /api/v1/chat endpoint returns.
// The LLM emits raw task IDs (no "task:" prefix) — DataflowView prepends it.
const CHAT_SSE_HIGHLIGHT_T1 = [
  'event: ui:highlight',
  'data: {"task_ids":["t1"]}',
  '',
  '',
].join('\n');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Register mock responses for all endpoints used by the workflow detail page.
 * Catch-all registered FIRST (lowest priority); specific routes LAST (highest priority).
 */
async function mockApis(page: Page) {
  await page.route("**/api/v1/**", (route) =>
    route.fulfill({ status: 404, json: { detail: "not mocked" } }),
  );
  await page.route("**/api/v1/info", (route) =>
    route.fulfill({ json: { service: "flowcept", version: "test" } }),
  );
  await page.route("**/api/v1/stats/tasks/summary**", (route) =>
    route.fulfill({ json: TASK_SUMMARY }),
  );
  await page.route("**/api/v1/tasks/query", (route) =>
    route.fulfill({ json: TASKS }),
  );
  // Dataflow registered before the shorter workflow route (LIFO: checked first).
  await page.route(`**/api/v1/workflows/${WF_ID}/dataflow`, (route) =>
    route.fulfill({ json: DATAFLOW }),
  );
  await page.route(`**/api/v1/workflows/${WF_ID}`, (route) =>
    route.fulfill({ json: WORKFLOW }),
  );
  // Chat: return a single SSE ui:highlight event then close the stream.
  await page.route("**/api/v1/chat", (route) =>
    route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
      body: CHAT_SSE_HIGHLIGHT_T1,
    }),
  );
}

/** Read the inline opacity of a ReactFlow node by its node ID. */
async function nodeOpacity(page: Page, nodeId: string): Promise<number> {
  return page
    .locator(`.react-flow__node[data-id="${nodeId}"]`)
    .evaluate((el) => parseFloat((el as HTMLElement).style.opacity || "1"));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("LLM highlight — Provenance Graph lineage dimming", () => {
  test.beforeEach(async ({ page }) => {
    await mockApis(page);
    await page.goto(`/workflows/${WF_ID}?tab=graph`);
    await page.getByRole("button", { name: "Provenance Graph" }).click();
    await page.locator(".react-flow__viewport").waitFor({ state: "visible" });
    // Let fitView animation finish.
    await page.waitForTimeout(400);
  });

  test("chat ui:highlight dims unrelated chain and brightens full lineage", async ({ page }) => {
    // Submit a chat message to trigger the mocked SSE response.
    await page.getByPlaceholder("Ask about your workflows… (Enter to send)").fill("show lineage of t1");
    await page.keyboard.press("Enter");

    // Wait for the highlight confirmation pill in the chat transcript.
    await page
      .getByText("Highlighted 1 task in the Provenance graph.")
      .waitFor({ state: "visible", timeout: 8_000 });

    // Chain A (task:t1 and its full lineage) must NOT be dimmed.
    for (const id of ["task:t1", "chunk:0", "task:t2"]) {
      const op = await nodeOpacity(page, id);
      expect(op, `${id} should be bright (in lineage)`).toBeGreaterThan(0.5);
    }

    // Chain B must be dimmed.
    for (const id of ["task:t3", "chunk:1", "task:t4"]) {
      const op = await nodeOpacity(page, id);
      expect(op, `${id} should be dimmed (not in lineage)`).toBeLessThan(0.5);
    }
  });

  test("Clear button restores all nodes to full opacity", async ({ page }) => {
    // Trigger highlight.
    await page.getByPlaceholder("Ask about your workflows… (Enter to send)").fill("show lineage of t1");
    await page.keyboard.press("Enter");
    await page
      .getByText("Highlighted 1 task in the Provenance graph.")
      .waitFor({ state: "visible", timeout: 8_000 });

    // Verify chain B is dimmed before clearing.
    expect(await nodeOpacity(page, "task:t3")).toBeLessThan(0.5);

    // Click the "Clear" button inside the highlight pill (exact match avoids
    // collision with the "Clear conversation" button in the chat header).
    await page.getByRole("button", { name: "Clear", exact: true }).click();

    // All nodes should return to full opacity.
    for (const id of ["task:t1", "chunk:0", "task:t2", "task:t3", "chunk:1", "task:t4"]) {
      const op = await nodeOpacity(page, id);
      expect(op, `${id} should be at full opacity after clear`).toBeGreaterThan(0.5);
    }
  });

  test("backward lineage: highlighting t2 also includes chunk:0 and task:t1", async ({ page }) => {
    // Override the chat mock to highlight t2 instead of t1.
    await page.route("**/api/v1/chat", (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: [
          'event: ui:highlight',
          'data: {"task_ids":["t2"]}',
          '',
          '',
        ].join('\n'),
      }),
    );

    await page.getByPlaceholder("Ask about your workflows… (Enter to send)").fill("show lineage of t2");
    await page.keyboard.press("Enter");
    await page
      .getByText("Highlighted 1 task in the Provenance graph.")
      .waitFor({ state: "visible", timeout: 8_000 });

    // Backward BFS from task:t2 should walk back through chunk:0 to task:t1.
    for (const id of ["task:t1", "chunk:0", "task:t2"]) {
      const op = await nodeOpacity(page, id);
      expect(op, `${id} should be bright (backward lineage of t2)`).toBeGreaterThan(0.5);
    }

    // Chain B still dimmed.
    for (const id of ["task:t3", "chunk:1", "task:t4"]) {
      const op = await nodeOpacity(page, id);
      expect(op, `${id} should be dimmed`).toBeLessThan(0.5);
    }
  });
});
