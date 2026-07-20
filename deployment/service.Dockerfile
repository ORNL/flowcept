# service.Dockerfile — Flowcept service image for Kubernetes deployment.
#
# Distinct from deployment/Dockerfile (the dev/test image used by `make build`
# and run-tests-in-container.yml). This one is slim and self-contained:
#   - builds the web UI and bakes it into the package (served by the webservice at /)
#   - installs only the service extras (webservice + redis + mongo + llm_agent)
#     (MongoDB Atlas uses public CAs already in the base image trust store — no CA bundle needed)
#
# Published to GHCR by the release workflow and mirrored to ECR via pull-through
# cache. The deployed Pods override CMD: `--start-webservice` (:8008) and
# `--start-agent` (:8003).

# ---- Stage 1: build the web UI ----
FROM node:22-slim AS ui-build
WORKDIR /app
COPY ui/package.json ui/package-lock.json ui/
RUN npm ci --prefix ui --no-audit --no-fund
COPY ui/ ui/
# vite.config.ts outDir = ../src/flowcept/webservice/ui_build → writes to /app/src/...
RUN npm run build --prefix ui

# ---- Stage 2: Flowcept runtime ----
FROM condaforge/miniforge3:23.11.0-0
WORKDIR /flowcept

COPY pyproject.toml Makefile README.md ./
COPY src ./src
COPY resources ./resources

# Built UI so the FastAPI webservice can serve it at /
COPY --from=ui-build /app/src/flowcept/webservice/ui_build ./src/flowcept/webservice/ui_build

# Escape hatch for building behind a corporate TLS-intercepting proxy (Netskope/Zscaler,
# etc.), which makes conda/pip fail with CERTIFICATE_VERIFY_FAILED. Default OFF (secure),
# so CI / off-network builds are unaffected. Local build behind such a proxy:
#   docker build --build-arg INSECURE_TLS=true -f deployment/service.Dockerfile -t flowcept-service:local .
ARG INSECURE_TLS=false
RUN if [ "$INSECURE_TLS" = "true" ]; then \
      echo "WARNING: INSECURE_TLS=true — disabling conda/pip TLS verification (use for local builds only)"; \
      conda config --system --set ssl_verify false; \
      printf '[global]\ntrusted-host = pypi.org files.pythonhosted.org pypi.python.org\n' > /etc/pip.conf; \
    fi

RUN conda create -n flowcept python=3.11.10 -y
RUN conda run -n flowcept pip install -e ".[webservice,redis,mongo,llm_agent]"

ENV FLOWCEPT_SETTINGS_PATH=/root/.flowcept/settings.yaml

# Default command; Kubernetes Deployments override this (webservice vs agent).
CMD ["conda", "run", "--no-capture-output", "-n", "flowcept", "flowcept", "--start-webservice"]
