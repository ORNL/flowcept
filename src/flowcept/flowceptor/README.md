# `flowcept.flowceptor`

Runtime interception layer. This package observes work, captures telemetry, publishes messages, and runs consumers.

## Key Areas

- `adapters/base_interceptor.py`: common interceptor lifecycle and message publishing.
- `adapters/instrumentation_interceptor.py`: bridge for explicit decorators/tasks.
- `adapters/dask/`: Dask worker plugin and task-state interception.
- `adapters/mlflow/`: MLflow DB/file watcher and run extraction.
- `adapters/tensorboard/`: TensorBoard event watcher.
- `adapters/brokers/`: broker message interception, currently MQTT.
- `consumers/base_consumer.py`: common MQ consumer loop.
- `consumers/document_inserter.py`: consumes task/workflow/object messages and persists metadata to the document DB.
- `consumers/agent/`: base context manager for MCP agents that consume Flowcept messages.
- `telemetry_capture.py`: CPU, memory, disk, network, process, and GPU telemetry capture.

## Message Path

1. Adapter or instrumentation creates a `TaskObject`, `WorkflowObject`, or object metadata message.
2. `BaseInterceptor` sends it through the configured MQ DAO.
3. Consumers receive messages from MQ.
4. `DocumentInserter` persists task/workflow metadata and ignores object metadata already handled by DBAPI when appropriate.

## Extension Rules

- New adapters should live under `adapters/<name>/` and use `BaseInterceptor`.
- Adapter settings should be dataclasses derived from `BaseSettings` and registered through `settings_factory.py`.
- Do not special-case one MQ backend in generic interceptor code.
- Shutdown/flush changes must be checked against Redis and Kafka paths.
- Tests usually belong in `tests/adapters/` or `tests/doc_db_inserter/`.
