# Local testing — Flowcept service image

Build and run the Flowcept **service image** (`deployment/service.Dockerfile`) locally to test the
**webservice** (REST API + built UI, port 8008) and, optionally, the **agent / MCP server**
(port 8003).

The service image bakes **no** `settings.yaml` (it only sets `FLOWCEPT_SETTINGS_PATH`), and the
services need **Redis** (MQ + KV) and **MongoDB**. Two ways to run it:

- **A. One command** with `compose-service.yml` (recommended) — builds the image and starts
  Redis + Mongo + the webservice together on one network.
- **B. Manual `docker run`** — more control; you start the deps and the container yourself.

---

## A. One command (compose)

```bash
# from the repo root
docker compose -f deployment/compose-service.yml up --build

# behind a corporate TLS-intercepting proxy (see Notes), prefix with INSECURE_TLS=true:
#   INSECURE_TLS=true docker compose -f deployment/compose-service.yml up --build
```

- Webservice + UI → <http://localhost:8008>
- Config comes from `deployment/local-settings.yaml` (mounted read-only; hosts are the compose
  service names `flowcept_redis` / `flowcept_mongo`). Edit that file to change settings, then re-run.
- Redis is published on `6379`, Mongo on `27017` (handy for pointing an instrumented script at the
  same Redis).

Start the **agent / MCP server** (port 8003) **and the Streamlit chat GUI** (port 8501) too —
requires `agent.enabled: true` + the LLM fields in `local-settings.yaml`:

```bash
docker compose -f deployment/compose-service.yml --profile agent up --build
```

The `agent` profile brings up two extra services:

- `flowcept_agent` — the MCP server (`http://localhost:8003/mcp`).
- `flowcept_agent_gui` — a Streamlit chat UI at **<http://localhost:8501>** that talks to the agent
  (it's an MCP client; `AGENT_HOST` is set to `flowcept_agent`). Use this to chat with the agent.
  The GUI calls the agent, and the **agent** calls the LLM (`llm_server_url`) — so the LLM must be
  reachable from the `flowcept_agent` container, not from the GUI.

Tear down (the `-v` also drops the Mongo data volume):

```bash
docker compose -f deployment/compose-service.yml down -v
```

### Agent chat needs a reachable LLM

The chat path is GUI → `flowcept_agent` → **LLM** (`agent.llm_server_url`). The agent must be able to
reach **and TLS-verify** that endpoint. Two common local snags and how to handle them:

**The internal endpoint isn't reachable / its TLS is intercepted.** If `agent.llm_server_url` points
at an internal service (e.g. `https://api.i2-core.american-science-cloud.org/`), a local run may fail
with `Connection error`, and the agent logs show the OpenAI client `Retrying request to
/chat/completions`. Diagnose from inside the agent container:

```bash
docker compose -f deployment/compose-service.yml exec flowcept_agent \
  curl -sS -v -m 10 https://api.i2-core.american-science-cloud.org/chat/completions 2>&1 | tail -25
```
- timeout / can't resolve / refused → endpoint is VPN/cluster-only; use **Option A** below.
- `self signed certificate in certificate chain` → a corporate TLS-intercepting proxy; use **Option A**
  (no TLS) or **Option B** (trust the proxy CA).

> This is a **local-only** issue — deployed cluster pods don't go through your laptop's proxy and
> verify the real cert normally, so don't change `llm_server_url` in the cluster manifest.

**Option A — local Ollama (HTTP, no TLS; simplest).** Avoids reachability and proxy-TLS entirely:

```bash
ollama serve && ollama pull llama3.1
```
In `deployment/local-settings.yaml` → `agent`:
```yaml
  llm_server_url: "http://host.docker.internal:11434/v1"
  api_key: "ollama"          # dummy non-empty value
  model: "llama3.1"          # a model you've pulled
  service_provider: "openai" # Ollama speaks the OpenAI protocol
```
```bash
docker compose -f deployment/compose-service.yml --profile agent up -d --force-recreate flowcept_agent
```

**Option B — keep the internal/HTTPS LLM, trust the corporate CA.** Use the overlay
`compose-service.corp-ca.yml`, which mounts your proxy's root CA and appends it to certifi (which
httpx/openai use) before starting the agent + webservice:

```bash
# 1. export your corporate root CA(s) — do NOT commit the file:
security find-certificate -a -p /Library/Keychains/System.keychain > deployment/corp-ca.pem
# 2. run with both compose files:
docker compose -f deployment/compose-service.yml -f deployment/compose-service.corp-ca.yml \
  --profile agent up --build
# (behind the proxy the build also needs INSECURE_TLS=true — prefix the command with it)
```

Either way, confirm the non-LLM path independently — `check_liveness` and DB tools don't need the LLM:
```bash
docker compose -f deployment/compose-service.yml exec -e AGENT_HOST=localhost \
  flowcept_agent conda run --no-capture-output -n flowcept flowcept --agent-client check_liveness
```

---

## B. Manual `docker run`

### 1. Build the image

```bash
docker build -f deployment/service.Dockerfile -t flowcept-service:local .

# behind a corporate TLS-intercepting proxy (see Notes):
#   docker build --build-arg INSECURE_TLS=true -f deployment/service.Dockerfile -t flowcept-service:local .
```

### 2. Start the dependencies

```bash
docker compose -f deployment/compose.yml up -d   # flowcept_redis:6379, flowcept_mongo:27017 (+ grafana)
```

### 3. Create a local `settings.yaml`

For the manual path the container reaches host-published ports via `host.docker.internal` (macOS;
on Linux add `--add-host=host.docker.internal:host-gateway` to the run commands):

```bash
sed -e 's/flowcept_redis/host.docker.internal/g' \
    -e 's/flowcept_mongo/host.docker.internal/g' \
    deployment/local-settings.yaml > local-settings.host.yaml
```

### 4. Run the webservice (port 8008)

```bash
docker run --rm -p 8008:8008 \
  -v "$PWD/local-settings.host.yaml:/root/.flowcept/settings.yaml:ro" \
  --name flowcept-web \
  flowcept-service:local
```

### 5. (Optional) Run the agent / MCP server (port 8003)

Set `agent.enabled: true` + the LLM fields in the settings first, then:

```bash
docker run --rm -p 8003:8003 \
  -v "$PWD/local-settings.host.yaml:/root/.flowcept/settings.yaml:ro" \
  --name flowcept-agent \
  flowcept-service:local \
  conda run --no-capture-output -n flowcept flowcept --start-agent
```

### 6. Tear down

```bash
docker rm -f flowcept-web flowcept-agent 2>/dev/null
docker compose -f deployment/compose.yml down        # add -v to also drop the mongo volume
```

---

## Verify (either path)

```bash
curl -I http://localhost:8008/openapi.json      # expect 200
open http://localhost:8008                       # the built UI (xdg-open on Linux)
# end-to-end: run an instrumented script publishing to the same Redis → it lands in Mongo → shows in the UI
```

---

## Notes

- **`db_flush_mode: online`** is required in the settings because MongoDB + KV are enabled; Flowcept's
  `validate_config()` rejects `offline` with persistent DBs enabled.
- **TLS/CA not needed locally:** the CA bundle baked into the image is only for DocumentDB; local
  Mongo is plain (no `tls=` / `retryWrites=` params).
- **Corporate TLS-intercepting proxy (Netskope/Zscaler, etc.):** if `docker build` fails at
  `conda create` / `pip install` with `CERTIFICATE_VERIFY_FAILED` / "self-signed certificate in
  certificate chain", your proxy is intercepting `conda.anaconda.org` / PyPI and the build container
  doesn't trust the proxy's root CA. Build with **`INSECURE_TLS=true`** (the `--build-arg` /
  compose env shown above) to bypass verification for the build. This is a **local-build escape hatch
  only** — it's off by default, so CI and off-network builds stay secure. The proper alternative is to
  bake your corporate root CA into the image and point `conda`/`pip` at it (`CONDA_SSL_VERIFY` /
  `REQUESTS_CA_BUNDLE`), if you can obtain the CA PEM.
- **`local-settings.yaml` is a dev artifact**, not the deployed config — the cluster uses a ConfigMap
  + secret env vars (see `../docs/deployment/amsc-i2-dev.md`).
- **Faster, no-Docker alternative:** `pip install -e ".[webservice,redis,mongo,llm_agent]"`, then
  `make services-mongo` and `make webservice` (or `flowcept --start-webservice`). Use the image path
  when you specifically want to validate the image.
