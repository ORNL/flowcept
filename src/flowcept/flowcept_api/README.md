# `flowcept.flowcept_api`

Public Python-facing control and query layer.

## Key Files

- `flowcept_controller.py`: defines `Flowcept`, the main context manager/controller. It starts/stops interceptors, persistence, workflow registration, reports, services, and utility APIs.
- `db_api.py`: high-level database API exposed through `Flowcept.db`. It routes task, workflow, and object operations to the configured document DAO.

## Runtime Flow

1. User enters `with Flowcept(...):` or calls `Flowcept().start()`.
2. The controller validates config, creates workflow metadata, and starts interceptors/consumers as configured.
3. Instrumentation/adapters emit task, workflow, and object messages.
4. `Flowcept.db` queries persisted data through `DBAPI`.
5. `Flowcept.stop()` flushes buffers and stops runtime resources.

## Object Save vs Query Split

`Flowcept` owns the **write path** for objects: `Flowcept.insert_or_update_object`, `Flowcept.insert_or_update_torch_model`, `Flowcept.insert_or_update_dataset`, and `Flowcept.insert_or_update_ml_model`. These methods persist to the DB **and** emit an object provenance message (including `created_at` / `updated_at` epoch timestamps) to the MQ buffer. They require an active `Flowcept` context and raise loudly if none exists.

`Flowcept.db` (`DBAPI`) is the **query-only** API. Its private `_insert_or_update_*` methods are internal helpers called by the controller; they accept a `BlobObject`, enrich it with timing, and return the same instance — they do not emit MQ messages.

## Extension Rules

- Keep user-facing orchestration in `Flowcept`; keep direct database operations in `DBAPI`.
- Do not read environment variables here; use values centralized by `configs.py`.
- New object save methods belong on `Flowcept` (controller), not on `DBAPI`. The DB write is delegated to `DBAPI._insert_or_update_object(blob_obj, object, ...)`; the MQ emit goes through `BaseInterceptor.send_object_message`.
- Tests for this package usually belong in `tests/api/`.
