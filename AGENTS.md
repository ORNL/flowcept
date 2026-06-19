# Flowcept Code Assistant Instructions

This file is the single source of truth for code-assistant behavior in this repository.
Each major module and the UI also has its own `README.md` (under `src/flowcept/*/`, `ui/`, `tests/`, `deployment/`, `examples/`) with deeper subsystem context; read the relevant one before working in that area.

Do not duplicate these rules in `CLAUDE.md`, `.cursor/rules`, `GEMINI.md`, `SKILL.md`, or other agent files.
If a tool requires its own file, make that file (which should immediately go to .gitignore) a thin pointer to this one.

## 1. First Principles

- Be surgical. Prefer small, reviewable changes.
- Reuse above all. Avoid duplication and one-off fixes. Duplicating code or logic is a MAJOR problem. Avoid it at all costs.
- Separation of concerns is extremely important in this project. Mixing concerns is not acceptable. Each module in the project has a clear and separate concern. Report if you find violations.
- Do not overengineer.
- Prefer visible failures over fallback code that hides contract mismatches.
- Prefer `settings.yaml` over hardcoded behavior.
- Avoid dependency pins unless there is a proven direct reason and no better practical fix.
- Do not commit personal absolute paths.
- Do not commit secrets or keys.
- Do not `pip install`; report missing packages and the command the user can run. Consider adding them to pyproject.toml.
- Do not auto-commit. Do not stage files automatically. The AI code assistant must test the fix/implemented feature and fix any error that appears before asking the user to test themselves. Do not ask to commit. 

## 2. Interaction Rules

- Keep responses under 50 words unless the user asks for detail.
- Do not dump large code or long explanations unless explicitly asked.
- Before long-running operations, warn the user and ask permission.
- During approved long operations, provide brief status updates about every minute.
- The human user is the owner and responsible for all actions in this code. Explain tradeoffs clearly, then follow decisions.

## 3. Editing Rules

- Read relevant code and tests before editing.
- Keep Python changes narrow, small, surgical, easy to review by a human.
- Before git commiting python files, run `make format`
- Use existing tests when possible. Add a new test file only when no existing file is a good home.
- Public functions/classes under `src/` need concise docstrings.
- Use `FlowceptLogger` for Flowcept warnings/errors, not `print`.
- Prefer `pathlib.Path` over `os.path`.
- Avoid local imports unless clearly necessary.
- Call static methods through the class name.

## 4. Git Rules

- Stage files explicitly:

```bash
git add path/to/file1 path/to/file2
```

- Never use `git add -A` or `git add .`.
- Never stage personal local instruction files.
- Never amend commits unless the user explicitly asks.
- Never revert user changes without explicit approval.

## 5. Paths And Scratch Work

- `agent_sandbox/` is the assistant scratch area (gitignored — never committed).
- Put plans and handoffs under `agent_sandbox/plans/`.
- Do not create scratch scripts in source, tests, docs, or `/tmp` when `agent_sandbox/` is appropriate.
- Do not run full test suites against `agent_sandbox/`, `tmp_tests/`, generated workflow cards, caches, or local data artifacts.
- Deployment templates under `deployment/*.yaml` must use `${DATA_DIR}` placeholders for data paths.
- Personal absolute paths belong only in untracked local settings files.

### Current-task memory file

**`agent_sandbox/current_task.md`** is the single living document for the feature or issue actively being developed.

- **Read it at the start of every session** before doing any work, and re-read it whenever the task context seems unclear.
- **Update it continuously**: add TODOs as they are discovered, check them off when done, record open decisions, blockers, and feature-specific mandates that do not belong in the permanent `AGENTS.md`.
- **Archive it when the feature ships**: rename to `agent_sandbox/archive/<feature-name>.md` and create a fresh `current_task.md` for the next task.
- Keep it short — bullets, not prose. If it grows past ~100 lines, trim resolved items.

This file exists because context windows reset and session summaries lose nuance. It is the agent's external working memory for the current task.

## 6. Source Map

- `src/flowcept/cli.py`: CLI commands and settings/profile entry points.
- `src/flowcept/configs.py`: settings loading, env overrides, runtime constants.
- `src/flowcept/flowcept_api/`: main `Flowcept` controller and DB API.
- `src/flowcept/instrumentation/`: decorators, tasks, loops, PyTorch hooks.
- `src/flowcept/flowceptor/`: adapters, interceptors, telemetry, consumers.
- `src/flowcept/commons/`: dataclasses, DAOs, buffers, logging, shared utilities.
- `src/flowcept/agents/`: MCP agent server, client, tools, prompts, LLM wrappers.
- `src/flowcept/report/`: workflow card/report generation.
- `src/flowcept/webservice/`: FastAPI REST API.
- `resources/sample_settings.yaml`: canonical full settings template.
- `.github/workflows/`: CI truth.
- `Makefile`: local service/test/check commands.
- `tests/`: behavior truth.
- `examples/` and `notebooks/`: user-facing runnable usage.

## 7. Documentation Routing

Use the RST docs as the maintained user documentation. Do not recreate these guides in agent files.

- `docs/index.rst`: documentation table of contents.
- `docs/default_user_guide.rst`: recommended first read for workflow developers.
- `docs/quick_start.rst`: minimal offline start.
- `docs/setup.rst`: installation and optional dependency strategy.
- `docs/cli-reference.rst`: CLI commands, config profiles, adapter flags.
- `docs/prov_capture.rst`: capture APIs and instrumentation patterns.
- `docs/prov_query.rst`: Python API, CLI, buffer, and DB querying.
- `docs/prov_storage.rst`: MQ, MongoDB, LMDB, JSONL buffer behavior.
- `docs/telemetry_capture.rst`: telemetry configuration and captured fields.
- `docs/agent.rst`: Flowcept MCP agent usage.
- `docs/reporting.rst`: workflow cards and reports.
- `docs/rest_api.rst`: REST API usage.
- `docs/architecture.rst`: system architecture.
- `docs/task_schema.rst`: task record schema.
- `docs/workflow_schema.rst`: workflow record schema.
- `docs/blob_data.rst` and `docs/blob_schema.rst`: object/blob persistence.
- `docs/api-reference.rst`: public API reference.
- `docs/contributing.rst` and `CONTRIBUTING.md`: contributor workflow.

When a user asks how to use Flowcept, read the relevant RST first and answer from it.
When a user or code assistant needs to learn or use a Flowcept feature, read the relevant RST first.

## 8. Flowcept Usage Rules

- Copy the sample settings file `resources/sample_settings.yaml` to `agent_sandbox/settings.yaml` and set the `FLOWCEPT_SETTINGS_PATH` environment variable to point to it during local runs and tests. Do not modify the user's settings in the home directory (`~/.flowcept/settings.yaml`).
- Use `FLOWCEPT_SETTINGS_PATH` to isolate settings for tests or experiments.

- `flowcept --init-settings` creates settings.
- `flowcept --init-settings --full -y` creates the full template.
- `flowcept --config-profile <profile> -y` changes runtime mode.
- Adapter flags are additive, for example:

```bash
flowcept --init-settings --full --dask --mlflow -y
```

- Config behavior precedence is:
  1. Environment variables.
  2. Settings files.
  3. Hardcoded defaults in `src/flowcept/configs.py`.
- All config defaults and env-var reads must be centralized in `src/flowcept/configs.py`.
- Never hardcode config values in other parts of the codebase.
- For profile/CLI behavior, verify `src/flowcept/cli.py`, `resources/sample_settings.yaml`, `docs/cli-reference.rst`, and `.github/workflows/*.yml`.

## 9. Instrumentation Guidance

- Capture the minimum provenance needed to answer the user’s questions.
- Prefer coarse instrumentation in hot paths.
- Use `@flowcept_task` for simple function capture.
- Use `@flowcept` for a top-level workflow function.
- Use `with Flowcept():` for multi-step workflow contexts.
- Use `FlowceptTask` only when decorators cannot express the needed fields.
- Use `FlowceptLoop` for loop provenance.
- Use adapters for Dask, MLflow, TensorBoard, and other supported frameworks.
- For details, read `docs/prov_capture.rst` before writing instrumentation examples.

## 10. Testing And Services

**TDD is mandatory for both Python and UI/frontend.** Write the test first, watch it fail, then implement until it passes.

- **Python**: write a real integration test in `tests/` before the implementation. Guard service-dependent tests with `Flowcept.services_alive()` / `MONGO_ENABLED` skips. No mocks.
- **UI/Frontend**: write a vitest test in `ui/tests/` before adding new pure logic (store mutations, utility functions, graph algorithms). Use real data fixtures — no mocks, no DOM for pure-function and store tests. Component render tests are discouraged (fragile, high mock cost); test logic at the function/store level instead. Run with `make ui-test`.

Use the `flowcept` conda environment.

Common commands:

```bash
# Python: lint, format, docs
conda run -n flowcept make checks
conda run -n flowcept make reformat
conda run -n flowcept make docs

# Python: integration tests (require live Mongo + Redis)
conda run -n flowcept make tests
conda run -n flowcept make tests-offline
conda run -n flowcept make tests-notebooks

# UI: vitest unit tests (pure functions, stores, utilities — no browser)
make ui-test

# UI: Playwright E2E tests — mocked (no live services needed)
make ui-e2e

# UI: Playwright E2E live integration tests (require live Mongo + Redis + webservice + Vite dev server)
# FLOWCEPT_SETTINGS_PATH must point to a settings file with MongoDB enabled and telemetry_capture configured
# (same file used to start the webservice, e.g. agent_sandbox/settings.yaml)
FLOWCEPT_SETTINGS_PATH=agent_sandbox/settings.yaml E2E_LIVE=1 make ui-e2e
```

Service commands:

```bash
make services
make services-mongo
make services-kafka
make services-stop
make services-stop-mongo
make services-stop-kafka
```

Before starting services, check whether containers are already running.

Do not run tests from scratch/sandbox directories. Target `tests/` explicitly.

- Prefer real tests over mocks. Use real services, real data, and real LLMs when feasible.
- Avoid mock-heavy tests unless there is no practical alternative.
- When a test fails, the correct fix is almost always to fix the implementation code, not the test; the test itself is very rarely the culprit. Always resolve warnings at their source rather than silencing them.
- **Periodically recommend running the full integration test suites** (`make tests` and `E2E_LIVE=1 make ui-e2e`) — especially after merges, significant backend or UI changes, or when the user has been iterating quickly on a feature. Mocked tests alone are not sufficient to catch regressions against real services.
- **Tests must verify meaningful system behavior**, not code structure (file paths, imports, `hasattr` checks).


## 11. CI And Dependency Drift

Before changing config profiles, MQ/DB behavior, Dask shutdown, examples, or dependencies, inspect `.github/workflows/*.yml`.

Important CI surfaces:

- `checks.yml`: lint and docs.
- `run-tests.yml`: broad Redis and Kafka path on push/schedule.
- `run-tests-simple.yml`: Redis without Mongo.
- `run-tests-offline.yml`: full offline profile.
- `run-tests-kafka.yml`: Kafka + Mongo.
- `run-tests-all-dbs.yml`: Mongo and LMDB coverage.
- `run-tests-in-container.yml`: Docker image tests.
- `run-tests-py313.yml`: Python 3.13 subset.
- `run-llm-tests.yml`: LLM/Dask examples.
- `create-release-n-publish.yml`: release only; do not treat as normal test workflow.

Important CI constraints:

- PRs fan out across Redis, Kafka, Mongo, LMDB, offline, container, Python-version, notebook, and LLM paths.
- Container tests may need explicit `/opt/conda/envs/flowcept/bin/flowcept` and `/opt/conda/envs/flowcept/bin/pytest`.
- Redis/Mongo Docker images and unpinned Python packages can drift without code changes.
- Dask/Flowcept shutdown or message flushing changes must be checked against both Redis and Kafka paths.
- Cleanup code should use stable ownership fields such as workflow IDs and object metadata, not optional task payload fields.

When CI starts failing without relevant code changes:

- Identify the last passing and first failing scheduled run.
- Trace the failing test to the exact runtime path.
- Check unpinned Python packages on that path.
- Check Docker images in `deployment/*.yml`.
- Check GitHub runner changes only after package/service changes.
- Confirm with the smallest dependency-only change before rewriting Flowcept logic.
- If local and CI format checks disagree, compare Ruff versions first.

## 12. Assistant-Specific Configuration

The repository must not maintain multiple duplicated assistant instruction files.

- `AGENTS.md`: canonical file.
- `CLAUDE.md`: do not recreate it unless a tool strictly requires it; if required, it must only point to `AGENTS.md`.
- Cursor: do not duplicate rules in `.cursor/rules`. If Cursor requires a rule, make it a thin instruction to read `AGENTS.md`.
- Gemini/other assistants: configure them to read `AGENTS.md`; do not create duplicate `GEMINI.md` content.
- `SKILL.md`/`SKILLS.md`: do not use for Flowcept repo rules. If a future repeated workflow is too large for this file, first prefer RST docs or existing source/tests. Add a skill only after the user approves.
- We deliberately avoid Flowcept-specific skill files because they create another documentation surface to keep in sync. The maintained source of feature knowledge is the RST docs; this file only routes agents to the right docs and code.
- `docs/flowcept_for_agents.md`: should not duplicate this file. Prefer deleting it or reducing it to a pointer to `AGENTS.md` and the RST docs.

## 13. Staleness Rules

If docs and code disagree, verify in this order:

1. Source code and tests.
2. `resources/sample_settings.yaml`.
3. `.github/workflows/*.yml` and `Makefile`.
4. RST docs.
5. Markdown docs.

When you find stale documentation, fix the smallest maintained document instead of adding another note elsewhere.

Periodically offer to read the relevant RST and Markdown files to check for stale or duplicated documentation, especially after code, CLI, config, CI, or public API changes.

## 14. Web UI — Workflow / Campaign List Ordering

**Rule: list endpoints must return newest-first so that `docs[:limit]` yields the most recent items.**

The single source of truth is `src/flowcept/webservice/services/sorting.py` → `sort_docs_by_first_date_field`. It must sort **descending** (`reverse=True`) and use `float("-inf")` as the fallback key for docs without a date field (so undated docs sort last, not first).

All list routers — `workflows.py`, `tasks.py`, `objects.py`, `agents.py`, `campaigns.py` — call this function before slicing. If you change the sort direction or add a new list endpoint, make sure it also sorts descending before the limit slice.

The frontend `useVisibleWorkflows` hook re-sorts the received items by `utc_timestamp` descending as well. Both layers must agree on newest-first; if either is flipped, recent runs disappear from the UI.

## 15. Default Dashboard Configs — Two Locations Must Stay in Sync

The default dashboard chart configs live in two places that **must always match**:

1. `ui/public/default_dashboard_configs.json` — source of truth; served by the Vite dev server; edited here when adding/changing default charts.
2. `src/flowcept/webservice/ui_build/default_dashboard_configs.json` — built copy; this is what `dashboard_store.py` seeds into Mongo on first run (`_SEED_FILE` constant).

After editing `ui/public/default_dashboard_configs.json`, always copy it to the `ui_build` location:
```
cp ui/public/default_dashboard_configs.json src/flowcept/webservice/ui_build/default_dashboard_configs.json
```

**Mongo is seeded once (when the `dashboards` collection is empty).** If the collection already has documents, changing the seed file has no effect. To push updates to a running instance, update the Mongo records directly:
```python
import json
from flowcept.webservice.services.dashboard_store import get_dashboard_store
store = get_dashboard_store()
for doc in json.load(open("src/flowcept/webservice/ui_build/default_dashboard_configs.json")):
    store.save(doc)
```
