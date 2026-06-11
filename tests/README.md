# Tests

This directory is the behavior reference for Flowcept. Prefer extending existing tests over creating new files.

## Layout

- `api/`: `Flowcept`, `DBAPI`, task query, object, and report API behavior.
- `adapters/`: Dask, MLflow, TensorBoard, broker, and file observer behavior.
- `agent/`: MCP agent tools and prompt-handler behavior.
- `doc_db_inserter/`: message-consumer persistence behavior.
- `instrumentation_tests/`: decorators, explicit tasks, loops, and ML instrumentation.
- `misc_tests/`: logging, singleton, telemetry.
- `report/`: provenance report service behavior.
- `webservice/`: FastAPI import, endpoint, and integration tests.

## Running

Use the `flowcept` conda environment.

```bash
conda run -n flowcept make tests
conda run -n flowcept make tests-offline
conda run -n flowcept make tests-notebooks
```

Start services with Makefile targets when needed:

```bash
make services
make services-mongo
make services-kafka
```

## Test Rules

- Target `tests/` explicitly; do not run scratch directories.
- Prefer real services and real data when practical.
- Use skip/guard logic when an external service is intentionally unavailable.
- Do not mutate environment variables inside test code; set them at invocation.
- Keep long or local-only LLM smoke tests outside CI unless explicitly approved.
