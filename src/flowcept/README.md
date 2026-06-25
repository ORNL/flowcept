# `flowcept` Source Package

This directory contains the runtime package. Use this README as a code-orientation map; use `docs/*.rst` for user-facing behavior.

## Main Entry Points

- `__init__.py`: public imports such as `Flowcept`, `flowcept_task`, `FlowceptTask`, and loop helpers.
- `cli.py`: command-line interface, settings initialization, config profiles, service startup, reports, and DB query commands.
- `configs.py`: centralized runtime configuration. Environment variables override settings files, which override defaults in this file.
- `version.py`: package version used by build/release tooling.

## Major Subpackages

- `flowcept_api/`: `Flowcept` controller and DB query API.
- `instrumentation/`: explicit capture APIs: decorators, tasks, loops, PyTorch hooks.
- `flowceptor/`: interceptors, adapters, consumers, telemetry capture.
- `commons/`: shared dataclasses, DAOs, buffers, logging, serialization, sanitization.
- `agents/`: MCP agent server/client/tools/prompts.
- `report/`: workflow card and PDF report generation.
- `webservice/`: FastAPI read-only REST API.

## Code Rules

- Keep config defaults and env-var reads in `configs.py`; do not hardcode runtime config elsewhere.
- Keep public imports in `__init__.py` intentional and stable.
- Prefer adding behavior behind existing APIs before creating new public entry points.
- Read the local README in each subpackage before editing that area.
