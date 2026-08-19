---
name: agent-loop-provenance
description: Emit compact declared provenance annotations for Flowcept PROV-Agent-Loop capture when a code-assistant session needs explicit agentic-loop semantics such as objectives, plans, plan steps, loop iterations, evaluations, criteria, thoughts, observations, beliefs, decisions, mandates, memories, or lessons learned.
---

# Agent Loop Provenance

Emit sparse Declared Provenance Layer (DPL) annotations for agentic-loop concepts the runtime log cannot reliably infer. The Observed Provenance Layer (OPL) already captures raw prompts, final responses, model/tool calls, command arguments, raw outputs, timestamps, token usage, files, errors, and status. Do not duplicate those as DPL.

Use one compact JSON object inside each `<flowcept_event>...</flowcept_event>` block. Prefer internal/progress messages, avoid final user-visible answers, and read `references/flowcept-prov-agent-loop.md` only when you need the full Flowcept mapping.

## Core Rules

Emit DPL only when a semantic concept is created or materially changes.

Do not emit DPL for raw user prompts, final user-visible responses, raw tool calls/outputs, timestamps, token counts, file paths, diffs, or exit codes already visible to the runtime.

Do emit DPL for refined objectives/plans, plan-step and loop boundaries, evaluation start/end with criteria/result/decision, and declared `Thought`, `Observation`, `Belief`, `Decision`, `Mandate`, `Memory`, or `LessonLearned`.

DPL boundary tags are control markers, not retrospective notes. Before the first tool call, code edit, validation command, or substantive execution for a planned step, emit:

1. `PlanStepExecution started`.
2. `LoopIteration started`.
3. `Evaluation started` if the next action is a test, check, validation, metric inspection, or acceptance assessment.

Never close a `LoopIteration` or `PlanStepExecution` and then run another tool for the same work. If more work is needed, keep the loop open. If switching steps, close the current loop/step first, then open the next step/loop before doing work.

Keep at most one active `PlanStepExecution` and one active `LoopIteration` unless the user explicitly asks for nested work. Prefer no nesting for provenance clarity.

Do not write normal prose like "Need start step..." as an internal reminder. Emit the correct DPL tag or omit the note.

## Payload

Use this generic shape:

```json
{"layer":"DPL","class":"Evaluation","event":"started","label":"Run tests","criteria":["Tests pass"]}
```

Required:

- `layer`: always `"DPL"`.
- `class`: one canonical concept.
- `event`: only for boundary activities, `"started"` or `"finished"`.

Canonical classes:

`Objective`, `Plan`, `PlanStepExecution`, `LoopIteration`, `Evaluation`, `EvaluationCriteria`, `EvaluationResult`, `Thought`, `Observation`, `Belief`, `Decision`, `Mandate`, `Memory`, `LessonLearned`.

Useful fields: `label`, `summary`, `status`, `criteria`, `criteria_ids`, `command`, `result`, `decision`, `reason`, and `derived_from`.

Use these controlled values where possible: `status` as `finished`, `passed`, `failed`, `inconclusive`, `skipped`, `error`, or `unknown`; `decision` as `continue`, `stop`, `retry`, `revise_plan`, `escalate`, or `fail`; `reason` as `success`, `timeout`, `max_iterations`, `budget_exceeded`, `approval_denied`, `test_failure`, or `guardrail_violation`.

Do not invent runtime ids such as `session_id`, `turn_id`, `workflow_id`, `task_id`, or `parent_id`. The adapter owns ids and links. Use stable labels.

## Planning

When producing an implementation or experiment plan, make the execution structure explicit enough to replay as provenance.

Every plan should include one objective/summary, a `Steps` section with one bullet per executable unit, and evaluation criteria for the whole plan when relevant.

Each executable step must have a stable label and, if needed, a short description.

Recommended visible shape:

```markdown
**Steps**
- `Inspect tutorial`
  Identify runnable entrypoints and constraints.
- `Create local config`
  Create Conda/project configuration.
- `Run Step 1`
  Execute the small Step 1 workflow.
- `Validate persistence`
  Query the configured database.

**Evaluation criteria**
- Config files parse successfully.
- Step 1 completes or fails with a documented blocker.
- Expected workflow/task records are present.
```

When executing the plan, copy the label exactly from `Steps` into each `PlanStepExecution`. Do not start a step whose label was not present unless the plan was revised or the user introduced it.

If the plan changes materially, emit a `Decision` with `decision:"revise_plan"` and then produce the revised visible step labels before continuing.

## Step And Loop Boundaries

For every planned step actually reached:

```text
<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"started","label":"Create local config"}</flowcept_event>
<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started","label":"Create local config loop","summary":"Create and inspect the local configuration."}</flowcept_event>
```

Then do the work. Finish in reverse order:

```text
<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"finished","label":"Create local config loop","status":"finished","summary":"Configuration was created and inspected."}</flowcept_event>
<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"finished","label":"Create local config","status":"finished","summary":"Local configuration is ready."}</flowcept_event>
```

Do not emit `PlanStepExecution finished` until every loop, tool invocation, and evaluation belonging to that step has finished and been interpreted.

A loop is one bounded agentic cycle: assemble context, invoke the model or choose an action, run tools/actions, capture observations, evaluate when relevant, and decide whether to continue, retry, revise, escalate, or stop.

Use one loop per attempt. Start a new loop when:

- an evaluation finishes with `decision:"retry"`;
- a decision is `retry`, `revise_plan`, `escalate`, `fail`, or `stop`;
- a failed action changes command, environment, dependency, parameter, resource request, or strategy;
- an observation changes the working belief used by the next action;
- validation ends and a new validation attempt begins;
- a step switches between implementation, validation, or final inspection.

Bad ordering:

```text
<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"finished","label":"Run tests loop"}</flowcept_event>
```

Then running `pytest`. The tool is outside the loop.

Good ordering:

```text
<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"started","label":"Run tests"}</flowcept_event>
<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started","label":"Run tests loop"}</flowcept_event>
<flowcept_event>{"layer":"DPL","class":"Evaluation","event":"started","label":"Run tests","criteria":["Tests pass"],"command":"pytest"}</flowcept_event>
```

Run the command, interpret it, then emit `Evaluation finished`, semantic evidence, `LoopIteration finished`, and `PlanStepExecution finished`.

## Evaluation

Criteria describe what will be checked. An `Evaluation` task exists only when the check actually runs or the assessment is actually performed.

Before a validation/test/check command:

```text
<flowcept_event>{"layer":"DPL","class":"Evaluation","event":"started","label":"Focused tests","criteria":["Focused tests pass"],"command":"pytest tests/test_parser.py"}</flowcept_event>
```

After interpreting the result:

```text
<flowcept_event>{"layer":"DPL","class":"Evaluation","event":"finished","label":"Focused tests","status":"passed","decision":"continue","reason":"success","result":"Focused tests passed."}</flowcept_event>
```

After an evaluation, usually emit:

- `Observation`: what the result shows.
- `Belief`: accepted working knowledge used later.
- `Decision`: continue, retry, revise, stop, escalate, fail, or accept.
- `LessonLearned`: reusable knowledge from evaluation/failure/debugging/comparison. Required when a failure/retry/workaround teaches something useful beyond the immediate command.
- `Memory`: only information intentionally retained for later steps, sessions, or reruns.

Always emit `LessonLearned` when an evaluation/debugging cycle discovers a reusable rule, workaround, environment constraint, dependency constraint, command preference, validation shortcut, resource behavior, or failure cause. In particular, if an evaluation fails and the next attempt changes command, dependency, environment, parameter, resource request, or strategy, emit `LessonLearned` after the retry is understood. If useful for future local/Frontier reruns, also emit `Memory`.

Lesson-learned retry example:

```text
<flowcept_event>{"layer":"DPL","class":"Evaluation","event":"finished","label":"Run local tests","status":"failed","decision":"retry","reason":"test_failure","result":"pytest was unavailable in the active environment."}</flowcept_event>
<flowcept_event>{"layer":"DPL","class":"Observation","summary":"The validation failed before tests ran because pytest is not installed.","derived_from":"Run local tests"}</flowcept_event>
<flowcept_event>{"layer":"DPL","class":"Decision","decision":"retry","reason":"test_failure","summary":"Retry with uv run --with pytest."}</flowcept_event>
<flowcept_event>{"layer":"DPL","class":"LessonLearned","summary":"Use uv run --with pytest for this repo when pytest is not declared in the local environment."}</flowcept_event>
```

## Semantic Messages

Use semantic tags sparsely, but do not leave them absent in nontrivial DPL runs.

- `Thought`: concise reasoning-in-progress or next investigative direction.
- `Observation`: interpreted feedback from tool result, test, metric, UI state, log, or error. Raw output is not an observation.
- `Belief`: accepted working knowledge derived from evidence and used later.
- `Decision`: explicit control choice, scope choice, approval outcome, stop/continue/retry/revise/escalate/fail.
- `Mandate`: human/system instruction, permission, restriction, approval, denial, budget, policy, or constraint.
- `Memory`: information intentionally retained for later steps, turns, sessions, or experiments.
- `LessonLearned`: reusable operational knowledge derived from evaluation, failure, repair, retry, workaround, or comparison.

Examples:

```text
<flowcept_event>{"layer":"DPL","class":"Observation","summary":"The test failed because the config file was missing.","derived_from":"last_tool_result"}</flowcept_event>
<flowcept_event>{"layer":"DPL","class":"Belief","summary":"The project requires creating the config before running Step 1.","derived_from":"last_observation"}</flowcept_event>
<flowcept_event>{"layer":"DPL","class":"Decision","decision":"retry","reason":"test_failure","summary":"Create the config and rerun Step 1."}</flowcept_event>
<flowcept_event>{"layer":"DPL","class":"LessonLearned","summary":"Validate local configuration before launching larger Frontier runs."}</flowcept_event>
```

Minimum DPL evidence for evaluation-oriented runs:

- every executed plan step has `PlanStepExecution started/finished`;
- every executed plan step contains at least one `LoopIteration started/finished`;
- every meaningful tool/test/log/metric loop emits at least one `Observation`;
- every control-flow change emits a `Decision`;
- every executed validation emits `Evaluation started/finished`;
- nontrivial runs emit `Memory` or `LessonLearned` when reusable knowledge appears.
