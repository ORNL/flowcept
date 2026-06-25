# Deployment

This directory contains the Docker image definition and local service stacks used by
Flowcept development, CI, and small deployments.

## Build The Image

Use the wrapper script from the repository root:

```bash
bash deployment/build-image.sh
```

The default build is intentionally broad:

- image tag: `flowcept:latest`
- Python: `3.11.10`
- Python extras: `all`
- UI build: enabled
- default container command: `bash`

That default matches the container CI use case, where the same image is reused across
Redis, Kafka, MongoDB, LMDB, webservice, UI, and test paths.

### Build Options

Set these environment variables before calling `deployment/build-image.sh`.

| Variable | Default | Purpose |
|---|---:|---|
| `IMAGE_TAG` | `flowcept:latest` | Docker image tag. |
| `PYTHON_VERSION` | `3.11.10` | Python version for the conda env. Keep CI on 3.11 unless the full container matrix proves otherwise. |
| `EXTRAS` | `all` | Optional dependency group from `pyproject.toml`. Use `EXTRAS=""` for core-only. |
| `BUILD_UI` | `true` | Build the React/Vite UI into `src/flowcept/webservice/ui_build`. Set `false` to skip. |
| `FLOWCEPT_CMD` | `bash` | Default command run by the container. |
| `DOCKER_BUILD_ARGS` | empty | Extra raw args forwarded to `docker build`, such as `--no-cache`. |

Examples:

```bash
# CI/default-style image
bash deployment/build-image.sh

# Core-only Python package, skip UI
EXTRAS="" BUILD_UI=false IMAGE_TAG=flowcept:core bash deployment/build-image.sh

# Agent-focused image
EXTRAS="lmdb,telemetry,dev,llm_agent,extras" \
FLOWCEPT_CMD="flowcept --start-agent" \
IMAGE_TAG=flowcept:agent \
bash deployment/build-image.sh

# Webservice/UI image with fewer Python extras than [all]
EXTRAS="redis,mongo,telemetry,webservice,llm_agent,extras" \
FLOWCEPT_CMD="flowcept --start-webservice --webservice-host=0.0.0.0" \
IMAGE_TAG=flowcept:webservice \
bash deployment/build-image.sh
```

The Dockerfile exposes:

- `8000`: default MCP/agent service port.
- `8003`: common deployment override for the MCP/agent service.
- `8008`: FastAPI webservice and packaged web UI.
- `5173`: Vite UI development server.

When `BUILD_UI=true`, Docker runs the same npm commands used by the Makefile UI
targets:

```bash
npm ci --prefix ui --no-audit --no-fund
npm run build --prefix ui
```

## Why So Many Compose Files?

Flowcept supports several MQ/DB combinations. The compose files are intentionally
small and focused so tests and developers can start only the services they need.
They are not different application deployments; they are service profiles.

Use the `Makefile` targets when possible because CI uses them too.

| File | Make target | Purpose |
|---|---|---|
| `compose.yml` | `make services` | Minimal Redis-only stack. Useful for MQ/KVDB paths without MongoDB. |
| `compose-mongo.yml` | `make services-mongo` | Redis + MongoDB. This is the common local development stack for online persistence and the web UI. |
| `compose-kafka.yml` | `make services-kafka` | Redis + MongoDB + Kafka/ZooKeeper. Used to test the Kafka MQ backend. |
| `compose-mofka.yml` | `make services-mofka` | Mofka-only stack for the Mofka MQ backend. Mofka is specialized and harder to run than Redis/Kafka. |
| `compose-grafana.yml` | no primary CI target | Redis + MongoDB + Grafana image for dashboard experiments. |
| `compose-rabbitmq.yml` | upcoming `make services-rabbitmq` | Redis + MongoDB + RabbitMQ. This is expected from the upcoming `agent_refactor` merge. |

Stop targets remove attached volumes, so they delete local service data:

```bash
make services-stop
make services-stop-mongo
make services-stop-kafka
make services-stop-mofka
# upcoming after agent_refactor:
make services-stop-rabbitmq
```

## Upcoming RabbitMQ Stack

The pending `agent_refactor` branch adds `deployment/compose-rabbitmq.yml` and Makefile
targets for RabbitMQ:

```bash
make services-rabbitmq
make services-stop-rabbitmq
make tests-in-container-rabbitmq
```

The RabbitMQ compose stack contains:

- Redis on `6379`.
- MongoDB on `27017`.
- RabbitMQ AMQP on `5672`.
- RabbitMQ management UI on `15672`.

The matching container test uses:

```bash
MQ_TYPE=rabbitmq
MQ_HOST=flowcept_rabbitmq
MQ_PORT=5672
MONGO_HOST=flowcept_mongo
```

After merging `agent_refactor`, keep this README and the Makefile/compose file names
in sync.

## Common Local Flows

Build and run with Redis + MongoDB:

```bash
make build
make services-mongo
make run
```

Run the webservice and packaged UI from the image:

```bash
FLOWCEPT_CMD="flowcept --start-webservice --webservice-host=0.0.0.0" \
IMAGE_TAG=flowcept:webservice \
bash deployment/build-image.sh

docker run --rm \
  -p 8008:8008 \
  -e MONGO_HOST=host.docker.internal \
  -e MQ_HOST=host.docker.internal \
  flowcept:webservice
```

Run container tests against MongoDB:

```bash
make build
make services-mongo
make tests-in-container-mongo
```
