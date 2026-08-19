# Flowcept PROV-Agent-Loop Mapping

## Capture Layers

Flowcept separates two capture layers:

- Observed Provenance Layer (OPL): deterministic records already present in the assistant/runtime log.
- Declared Provenance Layer (DPL): compact semantic annotations emitted by the agent or human when the runtime cannot infer meaning.

This skill only emits DPL. The adapter captures OPL separately.

## OPL Records

The adapter should capture these without DPL:

- `Session`
- `UserPrompt` when a real user request is observed
- `AgentResponse` from the final user-visible answer
- `AIModelInvocation`
- `ToolInvocation`
- raw tool results
- commands, arguments, working directories, sandbox/approval metadata
- timestamps, token usage, model/provider metadata
- file edits, errors, exit codes, diffs, and observable ids
- structural `LoopIteration` per turn when no semantic loop boundary is declared
- heuristic `Evaluation` for obvious test/check commands

Do not emit DPL just to repeat these records.

## DPL Records

Emit DPL for concepts that require semantic declaration:

- `Objective`
- `PlanStepExecution`
- semantic `LoopIteration`
- `Evaluation`, `EvaluationCriteria`, and `EvaluationResult`
- `Thought`
- `Observation`
- `Belief`
- `Decision`
- `Mandate`
- `Memory`
- `LessonLearned`

Use DPL only when a concept is created or materially changed.

## Flowcept Objects

Map PROV-Agent-Loop concepts to Flowcept records:

- `Session` -> `WorkflowObject`, `subtype: "session"`.
- `ExecutionPlan` -> `WorkflowObject`, `subtype: "execution_plan"`.
- `PlanStepExecution` -> `TaskObject`, `subtype: "plan_step_execution"`.
- `LoopIteration` -> `TaskObject`, `subtype: "loop_iteration"`.
- `AIModelInvocation` -> `TaskObject`, `subtype: "ai_model_invocation"`.
- `ToolInvocation` -> `TaskObject`, `subtype: "tool_invocation"`.
- `Evaluation` -> `TaskObject`, `subtype: "evaluation"`.
- `AIAgent` and `Human` -> `AgentObject`.
- `Objective`, `Plan`, `EvaluationCriteria`, `EvaluationResult`, raw tool inputs, and raw tool results -> entity dicts in `used.entities[]` or `generated.entities[]`.
- `Message`, `UserPrompt`, `AgentResponse`, `Thought`, `Observation`, `Belief`, `Decision`, `Mandate`, `Memory`, and `LessonLearned` -> message-like entity dicts in `used.messages[]` or `generated.messages[]`.

## DPL Payload Shape

Use one JSON object inside `<flowcept_event>...</flowcept_event>`:

```json
{"layer":"DPL","class":"Evaluation","event":"started","label":"Run tests","criteria":["Focused tests pass"]}
```

Required:

- `layer: "DPL"`
- `class`: the PROV-Agent-Loop class

Boundary activities use:

- `event: "started"`
- `event: "finished"`

Do not invent `session_id`, `turn_id`, `workflow_id`, `task_id`, or `parent_id`. The adapter creates these from the runtime log.

## Message Specializations

Use these distinctions:

- `Thought`: tentative intermediate reasoning or deliberation.
- `Observation`: perceived feedback derived from a tool, environment, evaluation, or other evidence.
- `Belief`: working knowledge accepted as true or likely true in the current loop/session.
- `Decision`: explicit control-flow choice, approval outcome, stop/retry/escalation/revision.
- `Mandate`: instruction, authorization, policy, or delegated constraint.
- `Memory`: persistent context promoted for reuse.
- `LessonLearned`: reusable operational learning.
Raw user prompts and final responses are OPL, not DPL.

## Used And Generated Shape

Flowcept keeps message-like entities under a stable `messages` key and non-message entities under an `entities` key:

```json
{
  "used": {
    "messages": [
      {"type": "observation", "content": "The previous validation failed because stderr was missing."}
    ],
    "entities": [
      {"type": "evaluation_criteria", "content": "Focused tests pass."}
    ]
  },
  "generated": {
    "entities": [
      {"type": "evaluation_result", "status": "passed", "content": "Focused tests passed."}
    ]
  }
}
```

Tool inputs and outputs are raw OPL entity records, not messages. Emit `Observation` only when the agent interprets the output:

```json
{"layer":"DPL","class":"Observation","summary":"The test failure shows the parser does not handle missing stderr.","derived_from":"last_tool_result"}
```

## Workflow And Task Links

The adapter infers links:

- `Session -> ExecutionPlan`
- `ExecutionPlan -> PlanStepExecution`
- `PlanStepExecution -> LoopIteration`
- `LoopIteration -> AIModelInvocation`
- `LoopIteration -> ToolInvocation`
- `LoopIteration -> Evaluation`

The agent helps by keeping labels stable:

- `label`: active plan step, loop, or evaluation label.
- `criteria`: evaluation criteria text.
- `criteria_ids`: only when naturally declared in a plan.
- `command`: test/check command.
- `derived_from`: obvious evidence label.

## Boundary Rules

- Prefer explicit start/end tags for semantic steps, loops, and evaluations.
- Every explicit test/check/validation should be associated with a loop iteration and evaluation when possible.
- Use `Decision` for retry, stop, revise-plan, escalate, or fail choices.
- Use `Memory` and `LessonLearned` only when information is intentionally promoted for future reuse.
- Keep annotations short; long outputs stay in raw logs or external records.
