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

## Extension Rules

- Keep user-facing orchestration in `Flowcept`; keep direct database operations in `DBAPI`.
- Do not read environment variables here; use values centralized by `configs.py`.
- Object persistence should go through `DBAPI`/DAO paths so object metadata messages stay consistent.
- Tests for this package usually belong in `tests/api/`.
