# Use the command `make build` to build this image.
# Use conda-forge base image consistently across local/CI.
FROM condaforge/miniforge3:23.11.0-0

ARG PYTHON_VERSION="3.11.10"
ARG EXTRAS="all"
ARG FLOWCEPT_CMD="bash"

WORKDIR /flowcept

COPY pyproject.toml Makefile README.md ./
COPY src ./src
COPY resources ./resources
COPY notebooks ./notebooks
COPY tests ./tests
COPY examples ./examples

ENV FLOWCEPT_SETTINGS_PATH=/flowcept/resources/sample_settings.yaml
ENV FLOWCEPT_CMD=${FLOWCEPT_CMD}

RUN conda create -n flowcept python=${PYTHON_VERSION} -y \
    && echo "conda activate flowcept" >> ~/.bashrc

# Keep [all] as the default because CI container tests exercise Redis, Kafka,
# MongoDB, LMDB, and dev/test dependencies. Pass EXTRAS="" to install only core.
RUN if [ -n "$EXTRAS" ]; then \
        conda run -n flowcept pip install -e ".[${EXTRAS}]"; \
    else \
        conda run -n flowcept pip install -e .; \
    fi

# 5000: legacy/default Flowcept web server port from sample settings.
# 8000: default Flowcept MCP/agent service port.
# 8003: common deployment override for the MCP/agent service.
# 8008: local FastAPI webservice port used by `make webservice`.
EXPOSE 5000 8000 8003 8008

CMD ["/bin/bash", "-lc", "conda run --no-capture-output -n flowcept ${FLOWCEPT_CMD}"]
