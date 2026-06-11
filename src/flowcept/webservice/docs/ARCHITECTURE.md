# Architecture Notes

## Design goals

1. Keep HTTP concerns isolated from storage/business code.
2. Reuse existing `DBAPI` to avoid duplicating datastore behavior.
3. Guarantee read-only behavior in v1.
4. Keep contract explicit via OpenAPI and typed schemas.

## Layering

- Router layer (`routers/*`)
  - HTTP parsing and response shaping
  - Path/query/body validation
  - endpoint-level error mapping
- Dependency layer (`deps.py`)
  - resolves `DBAPI` facade instance
- Service/util layer (`services/*`)
  - reusable serialization and normalization helpers
- Data backend (`flowcept_api.DBAPI` -> DAO)
  - all DB operations remain centralized in existing Flowcept stack

## Why this package is separate

`flowcept/flowcept_api` is a Python-facing API surface. `flowcept/webservice` is transport-facing (HTTP/OpenAPI). Keeping them separate prevents coupling transport details (status codes, query params, OpenAPI tags) into core provenance logic.

## Configuration strategy

No new config module is introduced in this package.

- Existing config source: `flowcept.configs`
- Existing web server settings are reused (`WEBSERVER_HOST`, `WEBSERVER_PORT`)

This avoids split-brain configuration and keeps deployment knobs centralized.

## Read-only guarantees

- Only `GET` and query `POST` routes exist.
- No write/upsert/delete routes in package.
- No raw Mongo pipeline execution endpoint is exposed in HTTP API v1.

## Future evolution

Potential additive changes without breaking v1:

- pagination with cursor tokens
- auth middleware (API key/OIDC)
- request IDs and structured access logs
- response caching for expensive read queries
- metrics and tracing middleware
