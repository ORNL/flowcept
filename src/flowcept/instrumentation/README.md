# `flowcept.instrumentation`

Explicit provenance capture APIs used directly in user code.

## Key Files

- `flowcept_decorator.py`: `@flowcept` workflow decorator.
- `flowcept_task.py`: `FlowceptTask` and task decorators.
- `flowcept_loop.py`: `FlowceptLoop` and lightweight loop capture.
- `flowcept_torch.py`: PyTorch module, epoch, batch, and child-layer capture.
- `flowcept_agent_task.py`: agent-aware task wrapper.
- `task_capture.py`: lower-level task capture helpers.

## Choosing An API

- Use `@flowcept_task` for simple function-level tasks.
- Use `@flowcept` for a top-level workflow function.
- Use `with Flowcept():` when the workflow spans multiple steps or files.
- Use `FlowceptTask` when decorators cannot express required fields.
- Use `FlowceptLoop` for loop iterations.
- Use `flowcept_torch.py` only for PyTorch-specific instrumentation.

## Extension Rules

- Instrument coarsely by default; tight loops and distributed workers can amplify overhead.
- Preserve `used`, `generated`, `activity_id`, `workflow_id`, and status semantics.
- Keep new instrumentation compatible with the existing interceptor path.
- Tests usually belong in `tests/instrumentation_tests/`.
