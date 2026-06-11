# `flowcept.commons`

Shared runtime building blocks used across Flowcept. Keep this package generic; domain-specific behavior belongs in the caller.

## Key Files

- `flowcept_dataclasses/`: message objects for tasks, workflows, blobs, telemetry, and adapter settings.
- `daos/docdb_dao/`: document database implementations for MongoDB and LMDB.
- `daos/mq_dao/`: message queue implementations for Redis, Kafka, and Mofka.
- `daos/keyvalue_dao.py`: Redis-backed key/value coordination used for safe stops and runtime bookkeeping.
- `autoflush_buffer.py`: size/time-based buffering before MQ flush.
- `settings_factory.py`: builds adapter settings objects from `settings.yaml`.
- `sanitization.py`: shared redaction helpers for secrets and sensitive values.
- `task_data_preprocess.py`: task summarization and schema helpers used by the agent.
- `utils.py`: serialization, time, git metadata, JSONL buffer, and utility helpers.
- `vocabulary.py`: shared enums and setting-key constants.

## Extension Rules

- Add new persisted fields to the dataclass first, then update schemas/docs/tests.
- Use `object_type` for object category; `type` is the message record type.
- Keep secret redaction reusable in `sanitization.py`.
- Add new storage backends behind the existing DAO interfaces instead of bypassing them.
- Avoid adding Flowcept-controller behavior here; this package should stay reusable.
