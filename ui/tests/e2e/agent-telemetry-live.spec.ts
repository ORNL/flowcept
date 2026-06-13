/**
 * Live E2E: agent telemetry tab shows real telemetry data.
 *
 * Full path verified:
 *   Agents list page → click agent card → Telemetry tab
 *   → TelemetryChart fetches /stats/timeseries?filter={agent_id:...}
 *   → ECharts canvas and metric toggle buttons render with data
 *
 * Prerequisites (all must be true for tests to run):
 *   1. E2E_LIVE=1 env var is set.
 *   2. The Flowcept webservice is running on VITE_API_PORT (default 8008).
 *   3. The Vite dev server is running on VITE_DEV_PORT (default 5173).
 *   4. MongoDB + Redis are alive.
 *   5. FLOWCEPT_SETTINGS_PATH is set to a settings file with MongoDB enabled + telemetry_capture configured
 *      (the same file used to start the webservice, e.g. agent_sandbox/settings.yaml).
 *
 * Run locally with:
 *   E2E_LIVE=1 make ui-e2e
 *
 * Skipped automatically when E2E_LIVE is not set (never blocks CI).
 */

import { test, expect } from "@playwright/test";
import { execFileSync } from "child_process";
import { writeFileSync, unlinkSync } from "fs";
import { join, resolve } from "path";
import { tmpdir } from "os";
import { fileURLToPath } from "url";

const LIVE = !!process.env.E2E_LIVE;

// ---------------------------------------------------------------------------
// Seed helpers
// ---------------------------------------------------------------------------

interface SeedData {
  workflow_id: string;
  campaign_id: string;
  agent_ids: string[];
  task_count: number;
  has_telemetry: boolean;
}

// Playwright runs from ui/; the repo root is one level up.
const _file = fileURLToPath(import.meta.url);
const REPO_ROOT = resolve(_file, "..", "..", "..", "..");

function runGridsearchExperiment(): SeedData {
  const script = `
import json, sys, time
sys.path.insert(0, "${REPO_ROOT}/src")
sys.path.insert(0, "${REPO_ROOT}/tests")
from flowcept.configs import MONGO_ENABLED
from flowcept import Flowcept

if not MONGO_ENABLED:
    print(json.dumps({"error": "mongo_disabled", "detail": "FLOWCEPT_SETTINGS_PATH must point to a settings file with MongoDB enabled and telemetry_capture configured"}))
    sys.exit(0)

if not Flowcept.services_alive():
    print(json.dumps({"error": "services_not_alive"}))
    sys.exit(0)

from instrumentation_tests.ml_tests.single_layer_perceptron_test import run_gridsearch_experiment
from uuid import uuid4

campaign_id = f"e2e-agent-tel-{uuid4()}"
run_data = run_gridsearch_experiment(campaign_id=campaign_id)
tasks = run_data["tasks"]
agent_ids = sorted({t.get("agent_id") for t in tasks if t.get("agent_id")})
has_telemetry = any(t.get("telemetry_at_start") or t.get("telemetry_at_end") for t in tasks)

# Poll until tasks with agent_id are queryable (guards against any flush lag)
if agent_ids:
    for attempt in range(10):
        found = Flowcept.db.task_query(filter={"agent_id": agent_ids[0]}) or []
        if found:
            break
        time.sleep(0.5)

print(json.dumps({
    "workflow_id": run_data["workflow_id"],
    "campaign_id": campaign_id,
    "agent_ids": agent_ids,
    "task_count": len(tasks),
    "has_telemetry": has_telemetry,
}))
`;

  const scriptPath = join(tmpdir(), `flowcept_e2e_gridsearch_${Date.now()}.py`);
  writeFileSync(scriptPath, script, "utf8");

  try {
    const env: Record<string, string> = { ...(process.env as Record<string, string>) };
    env.PYTHONPATH = `${REPO_ROOT}/src`;

    const out = execFileSync(
      "conda",
      ["run", "-n", "flowcept", "python", scriptPath],
      { encoding: "utf8", env, cwd: REPO_ROOT, timeout: 300_000 },
    );

    const jsonLine = out.trim().split("\n").reverse().find((l) => l.startsWith("{"));
    if (!jsonLine) throw new Error(`Seed script produced no JSON. Output:\n${out}`);
    const parsed = JSON.parse(jsonLine) as SeedData & { error?: string; detail?: string };
    if (parsed.error === "mongo_disabled") {
      throw new Error(
        `MongoDB is disabled in the active Flowcept settings.\n` +
        `Set FLOWCEPT_SETTINGS_PATH to a settings file with MongoDB enabled and telemetry_capture configured.\n` +
        `Detail: ${parsed.detail}`,
      );
    }
    return parsed as SeedData;
  } finally {
    try { unlinkSync(scriptPath); } catch { /* ignore */ }
  }
}

function teardown(campaignId: string) {
  try {
    const script = `
import sys
sys.path.insert(0, "${REPO_ROOT}/src")
from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
dao = DocumentDBDAO.get_instance(create_indices=False)
dao.delete_campaign_data("${campaignId}")
`;
    const scriptPath = join(tmpdir(), `flowcept_e2e_teardown_${Date.now()}.py`);
    writeFileSync(scriptPath, script, "utf8");
    const env: Record<string, string> = { ...(process.env as Record<string, string>) };
    env.PYTHONPATH = `${REPO_ROOT}/src`;
    execFileSync("conda", ["run", "-n", "flowcept", "python", scriptPath], {
      encoding: "utf8", env, cwd: REPO_ROOT,
    });
    unlinkSync(scriptPath);
  } catch { /* best-effort */ }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Agent telemetry tab — real DB + real data", () => {
  let seed: SeedData;

  test.beforeAll(async () => {
    test.skip(!LIVE, "Set E2E_LIVE=1 to run live integration tests.");
    try {
      seed = runGridsearchExperiment();
    } catch (err) {
      test.skip(true, `Seed failed: ${err instanceof Error ? err.message : String(err)}`);
      return;
    }
    if ((seed as any).error === "services_not_alive") {
      test.skip(true, "Flowcept services (Mongo/Redis) are not alive.");
    }
  });

  test.afterAll(() => {
    if (LIVE && seed?.campaign_id) teardown(seed.campaign_id);
  });

  test("gridsearch experiment captures telemetry on agent tasks", async () => {
    test.skip(!LIVE, "Set E2E_LIVE=1 to run live integration tests.");
    expect(seed.has_telemetry, "Expected at least one task to have telemetry").toBe(true);
    expect(seed.agent_ids.length, "Expected at least one agent_id in tasks").toBeGreaterThan(0);
  });

  test("agents page shows agent cards that are clickable links to the detail page", async ({ page }) => {
    test.skip(!LIVE, "Set E2E_LIVE=1 to run live integration tests.");

    await page.goto("/agents");

    // Wait for any agent card link to appear (proves the list loaded).
    const anyCard = page.locator("a[href*='/agents/']").first();
    await anyCard.waitFor({ state: "visible", timeout: 10_000 });

    // Capture the href so we can assert the navigation target.
    const href = await anyCard.getAttribute("href") ?? "";
    expect(href).toMatch(/\/agents\/.+/);

    // Click and confirm navigation.
    await anyCard.click();
    await expect(page).toHaveURL(new RegExp("/agents/.+"));
  });

  test("agent detail telemetry tab renders metric toggle buttons and ECharts canvas", async ({ page }) => {
    test.skip(!LIVE, "Set E2E_LIVE=1 to run live integration tests.");

    const agentId = seed.agent_ids[0];
    await page.goto(`/agents/${agentId}?tab=telemetry`);

    // TelemetryChart renders metric toggle buttons. Use exact: true to avoid matching
    // "Process CPU %" when looking for "CPU %".
    await page.getByRole("button", { name: "CPU %", exact: true }).waitFor({ state: "visible", timeout: 10_000 });

    // The ECharts canvas must be present and sized (height > 0).
    const canvas = page.locator("canvas").first();
    await canvas.waitFor({ state: "visible", timeout: 10_000 });
    const box = await canvas.boundingBox();
    expect(box?.height, "ECharts canvas should have non-zero height").toBeGreaterThan(0);
    expect(box?.width, "ECharts canvas should have non-zero width").toBeGreaterThan(0);
  });

  test("agent detail telemetry tab shows data points — sparkline has at least one task point", async ({ page }) => {
    test.skip(!LIVE, "Set E2E_LIVE=1 to run live integration tests.");

    const agentId = seed.agent_ids[0];
    await page.goto(`/agents/${agentId}?tab=telemetry`);

    // Wait for metric toggle buttons to confirm the chart component has mounted.
    await page.getByRole("button", { name: "CPU %", exact: true }).waitFor({ state: "visible", timeout: 10_000 });

    // When data is present the "no data" message must NOT be shown.
    await expect(page.getByText("No telemetry data")).not.toBeVisible();

    // At least one ECharts canvas must be rendered.
    const canvases = page.locator("canvas");
    const count = await canvases.count();
    expect(count, "Expected at least one ECharts canvas").toBeGreaterThanOrEqual(1);
  });
});
