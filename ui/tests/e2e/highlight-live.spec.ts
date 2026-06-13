/**
 * Live end-to-end highlight test — no mocks, real LLM, real DB.
 *
 * This test covers the full stack:
 *   Browser → Vite proxy → FastAPI → LLM → highlight_lineage tool
 *   → SSE event: ui:highlight → ChatPanel → highlightStore → DataflowView → DOM opacity
 *
 * Prerequisites (all must be true for the test to run):
 *   1. E2E_LIVE=1 env var is set.
 *   2. The Flowcept webservice is running on port 8008 (VITE_API_PORT).
 *   3. The Vite dev server is running on port 5173 (or whatever VITE_DEV_PORT is).
 *   4. MongoDB + Redis are alive.
 *   5. agent.api_key and agent.service_provider are set in settings.yaml.
 *   6. PYTHONPATH=src and FLOWCEPT_SETTINGS_PATH point to a valid settings file.
 *
 * Run locally with:
 *   E2E_LIVE=1 make ui-e2e
 *
 * Skipped automatically when E2E_LIVE is not set (never blocks CI).
 */

import { test, expect, type Page } from "@playwright/test";
import { execFileSync, execSync } from "child_process";
import { writeFileSync, unlinkSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";

// ---------------------------------------------------------------------------
// Guard: skip the entire file when E2E_LIVE is not set.
// ---------------------------------------------------------------------------

const LIVE = !!process.env.E2E_LIVE;

// ---------------------------------------------------------------------------
// Helpers shared with the mocked highlight spec.
// ---------------------------------------------------------------------------

async function nodeOpacity(page: Page, nodeId: string): Promise<number> {
  return page
    .locator(`.react-flow__node[data-id="${nodeId}"]`)
    .evaluate((el) => parseFloat((el as HTMLElement).style.opacity || "1"));
}

async function wheelOnCanvas(page: Page, deltaY: number, times = 3) {
  const canvas = page.locator(".react-flow");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("ReactFlow canvas not found");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  for (let i = 0; i < times; i++) await page.mouse.wheel(0, deltaY);
  await page.waitForTimeout(200);
}

// ---------------------------------------------------------------------------
// DB seeding via Python (runs in the flowcept conda env).
// ---------------------------------------------------------------------------

interface SeedData {
  workflow_id: string;
  step_a_id: string;
  step_b_id: string;
  campaign_id: string;
}

function seedWorkflow(): SeedData {
  const script = `
import json, sys
from uuid import uuid4
from flowcept import Flowcept, FlowceptTask
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject

if not Flowcept.services_alive():
    print(json.dumps({"error": "services_not_alive"}))
    sys.exit(0)

campaign_id = f"e2e-live-hl-{uuid4()}"
with Flowcept(campaign_id=campaign_id, workflow_name="e2e-live-hl-wf"):
    wf_id = Flowcept.current_workflow_id
    with FlowceptTask(activity_id="step_a", used={"x": 1}) as task_a:
        task_a.end(generated={"y": 2})
    step_a_id = task_a.get_id()
    with FlowceptTask(activity_id="step_b", used={"y": 2}) as task_b:
        task_b.end(generated={"z": 3})
    step_b_id = task_b.get_id()

import time
deadline = time.time() + 20
while time.time() < deadline:
    rows = Flowcept.db.task_query(filter={"workflow_id": wf_id}) or []
    if len(rows) >= 2:
        break
    time.sleep(0.3)

print(json.dumps({
    "workflow_id": wf_id,
    "step_a_id": step_a_id,
    "step_b_id": step_b_id,
    "campaign_id": campaign_id,
}))
`;

  const scriptPath = join(tmpdir(), `flowcept_e2e_seed_${Date.now()}.py`);
  writeFileSync(scriptPath, script, "utf8");

  try {
    const env: Record<string, string> = {
      ...process.env as Record<string, string>,
      PYTHONPATH: "src",
    };
    // Propagate settings path if provided.
    if (process.env.FLOWCEPT_SETTINGS_PATH) {
      env.FLOWCEPT_SETTINGS_PATH = process.env.FLOWCEPT_SETTINGS_PATH;
    }

    const out = execFileSync(
      "conda",
      ["run", "-n", "flowcept", "python", scriptPath],
      { encoding: "utf8", env, cwd: process.cwd() },
    );

    // Last non-empty line is the JSON output from the script.
    const jsonLine = out.trim().split("\n").reverse().find((l) => l.startsWith("{"));
    if (!jsonLine) throw new Error(`Seed script produced no JSON. Output:\n${out}`);
    return JSON.parse(jsonLine) as SeedData;
  } finally {
    try { unlinkSync(scriptPath); } catch { /* ignore */ }
  }
}

function teardownWorkflow(campaignId: string) {
  try {
    const script = `
from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
dao = DocumentDBDAO.get_instance(create_indices=False)
dao.delete_campaign_data("${campaignId}")
`;
    const scriptPath = join(tmpdir(), `flowcept_e2e_teardown_${Date.now()}.py`);
    writeFileSync(scriptPath, script, "utf8");
    const env: Record<string, string> = {
      ...process.env as Record<string, string>,
      PYTHONPATH: "src",
    };
    if (process.env.FLOWCEPT_SETTINGS_PATH) {
      env.FLOWCEPT_SETTINGS_PATH = process.env.FLOWCEPT_SETTINGS_PATH;
    }
    execFileSync("conda", ["run", "-n", "flowcept", "python", scriptPath], {
      encoding: "utf8", env, cwd: process.cwd(),
    });
    unlinkSync(scriptPath);
  } catch {
    /* best-effort cleanup */
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Live highlight integration — real LLM + real DB", () => {
  let seed: SeedData;

  test.beforeAll(async () => {
    test.skip(!LIVE, "Set E2E_LIVE=1 to run live integration tests.");
    seed = seedWorkflow();
    if ((seed as any).error === "services_not_alive") {
      test.skip(true, "Flowcept services (Mongo/Redis) are not alive.");
    }
  });

  test.afterAll(async () => {
    if (LIVE && seed?.campaign_id) teardownWorkflow(seed.campaign_id);
  });

  test("chat ui:highlight event dims unrelated nodes and brightens full lineage (real LLM)", async ({ page }) => {
    test.skip(!LIVE, "Set E2E_LIVE=1 to run live integration tests.");

    // Navigate to the workflow's graph tab — NO route mocks; all calls hit the real backend.
    await page.goto(`/workflows/${seed.workflow_id}?tab=graph`);
    await page.getByRole("button", { name: "Dataflow Graph" }).click();
    await page.locator(".react-flow__viewport").waitFor({ state: "visible" });
    await page.waitForTimeout(400);

    // Submit a natural-language request that should trigger highlight_lineage.
    const prompt = `Highlight the lineage of task ${seed.step_a_id} in the dataflow graph.`;
    await page.getByPlaceholder("Ask about your workflows… (Enter to send)").fill(prompt);
    await page.keyboard.press("Enter");

    // Wait up to 30 s for the LLM to respond and the highlight pill to appear.
    await page
      .getByText(/highlighted \d+ task/i)
      .waitFor({ state: "visible", timeout: 30_000 });

    // Seed nodes and their lineage must NOT be dimmed.
    const seedNodeId = `task:${seed.step_a_id}`;
    const seedOp = await nodeOpacity(page, seedNodeId);
    expect(seedOp, `Seed node ${seedNodeId} should be bright`).toBeGreaterThan(0.5);

    // At least one other node must be dimmed — verifies the contrast effect.
    // Zoom out a few times first so all nodes are visible, then sample them.
    await wheelOnCanvas(page, 120, 3);
    const allNodes = await page.locator(".react-flow__node").all();
    const opacities = await Promise.all(
      allNodes.map((n) => n.evaluate((el) => parseFloat((el as HTMLElement).style.opacity || "1"))),
    );
    const hasDimmed = opacities.some((op) => op < 0.5);
    expect(hasDimmed, "At least one node outside the lineage should be dimmed").toBe(true);

    // The chat transcript must show the highlight pill.
    await expect(page.getByText(/highlighted \d+ task/i)).toBeVisible();
  });

  test("Clear button removes highlight and all nodes return to full opacity (real LLM)", async ({ page }) => {
    test.skip(!LIVE, "Set E2E_LIVE=1 to run live integration tests.");

    await page.goto(`/workflows/${seed.workflow_id}?tab=graph`);
    await page.getByRole("button", { name: "Dataflow Graph" }).click();
    await page.locator(".react-flow__viewport").waitFor({ state: "visible" });
    await page.waitForTimeout(400);

    // Trigger the highlight.
    const prompt = `Highlight the lineage of task ${seed.step_a_id} in the dataflow graph.`;
    await page.getByPlaceholder("Ask about your workflows… (Enter to send)").fill(prompt);
    await page.keyboard.press("Enter");
    await page
      .getByText(/highlighted \d+ task/i)
      .waitFor({ state: "visible", timeout: 30_000 });

    // Click Clear.
    await page.getByRole("button", { name: "Clear", exact: true }).click();

    // After clear, all nodes must be at full opacity.
    await wheelOnCanvas(page, 120, 3);
    const allNodes = await page.locator(".react-flow__node").all();
    const opacities = await Promise.all(
      allNodes.map((n) => n.evaluate((el) => parseFloat((el as HTMLElement).style.opacity || "1"))),
    );
    const allFull = opacities.every((op) => op > 0.5);
    expect(allFull, "All nodes should be at full opacity after Clear").toBe(true);
  });
});
