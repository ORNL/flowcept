# Show help, place this first so it runs with just `make`
help:
	@printf "\nCommands:\n"
	@printf "\033[32mbuild\033[0m                     build the Docker image\n"
	@printf "\033[32mrun\033[0m                       run the Docker container\n"
	@printf "\033[32mliveness\033[0m                  check if the services are alive\n"
	@printf "\033[32mservices\033[0m                  run services using Docker\n"
	@printf "\033[32mservices-stop\033[0m             stop the running Docker services\n"
	@printf "\033[32mservices-mongo\033[0m            run services with MongoDB using Docker\n"
	@printf "\033[32mservices-stop-mongo\033[0m       stop MongoDB services and remove attached volumes\n"
	@printf "\033[32mservices-kafka\033[0m            run services with Kafka using Docker\n"
	@printf "\033[32mservices-stop-kafka\033[0m       stop Kafka services and remove attached volumes\n"
	@printf "\033[32mservices-mofka\033[0m            run services with Mofka using Docker\n"
	@printf "\033[32mservices-stop-mofka\033[0m       stop Mofka services and remove attached volumes\n"
	@printf "\033[32mtests\033[0m                     run unit tests with pytest\n"
	@printf "\033[32mtests-in-container\033[0m        run unit tests with pytest inside Flowcept's container\n"
	@printf "\033[32mtests-in-container-mongo\033[0m  run unit tests inside container with MongoDB\n"
	@printf "\033[32mtests-in-container-kafka\033[0m  run unit tests inside container with Kafka and MongoDB\n"
	@printf "\033[32mtests-notebooks\033[0m           test the notebooks using pytest\n"
	@printf "\033[32mclean\033[0m                     remove cache directories and Sphinx build output\n"
	@printf "\033[32mdocs\033[0m                      build HTML documentation using Sphinx\n"
	@printf "\033[32mchecks\033[0m                    run ruff linter and formatter checks\n"
	@printf "\033[32mreformat\033[0m                  run ruff linter and formatter\n"

# Run linter and formatter checks using ruff
checks:
	ruff check src
	ruff format --check src

reformat:
	ruff check src --fix --unsafe-fixes
	ruff format src

# Remove cache directories and Sphinx build output
clean:
	@sh -c 'rm -rf .ruff_cache .pytest_cache mnist_data tensorboard_events 2>/dev/null || true'
	@sh -c 'rm -f docs_dump_tasks_* dump_test.json 2>/dev/null || true'
	@find . -type d -name "*flowcept_lmdb*" -exec sh -c 'rm -rf "$$@" 2>/dev/null || true' sh {} +
	@find . -type f -name "*.log" -exec sh -c 'rm -f "$$@" 2>/dev/null || true' sh {} +
	@find . -type f -name "*.pth" -exec sh -c 'rm -f "$$@" 2>/dev/null || true' sh {} +
	@find . -type f -name "mlflow.db" -exec sh -c 'rm -f "$$@" 2>/dev/null || true' sh {} +
	@find . -type d -name "mlruns" -exec sh -c 'rm -rf "$$@" 2>/dev/null || true' sh {} +
	@find . -type d -name "__pycache__" -exec sh -c 'rm -rf "$$@" 2>/dev/null || true' sh {} +
	@find . -type d -name "*tfevents*" -exec sh -c 'rm -rf "$$@" 2>/dev/null || true' sh {} +
	@find . -type d -name "*output_data*" -exec sh -c 'rm -rf "$$@" 2>/dev/null || true' sh {} +
	@find . -type f -name "*nohup*" -exec sh -c 'rm -f "$$@" 2>/dev/null || true' sh {} +
	@sh -c 'sphinx-build -M clean docs docs/_build > /dev/null 2>&1 || true'

# Build the HTML documentation using Sphinx
.PHONY: docs
docs:
	sphinx-build -M html docs docs/_build

# Run services using Docker
services:
	docker compose --file deployment/compose.yml up --detach

# Stop the running Docker services and remove volumes attached to containers
services-stop:
	docker compose --file deployment/compose.yml down --volumes

# Run services using Docker
services-mongo:
	docker compose --file deployment/compose-mongo.yml up --detach

services-stop-mongo:
	docker compose --file deployment/compose-mongo.yml down --volumes

# Build a new Docker image for Flowcept
build:
	bash deployment/build-image.sh

# To use run, you must run make services first.
run:
	docker run --rm -v $(shell pwd):/flowcept -e KVDB_HOST=flowcept_redis -e MQ_HOST=flowcept_redis -e MONGO_HOST=flowcept_mongo --network flowcept_default -it flowcept

tests-in-container-mongo:
	docker run --rm -v $(shell pwd):/flowcept -e KVDB_HOST=flowcept_redis -e MQ_HOST=flowcept_redis -e MONGO_HOST=flowcept_mongo -e MONGO_ENABLED=true -e LMDB_ENABLED=false --network flowcept_default flowcept /opt/conda/envs/flowcept/bin/pytest --ignore=tests/instrumentation_tests/ml_tests

tests-in-container:
	docker run --rm -v $(shell pwd):/flowcept -e KVDB_HOST=flowcept_redis -e MQ_HOST=flowcept_redis -e MONGO_ENABLED=false -e LMDB_ENABLED=true --network flowcept_default flowcept /opt/conda/envs/flowcept/bin/pytest --ignore=tests/instrumentation_tests/ml_tests

tests-in-container-kafka:
	docker run --rm -v $(shell pwd):/flowcept -e KVDB_HOST=flowcept_redis -e MQ_HOST=kafka -e MONGO_HOST=flowcept_mongo  -e MQ_PORT=29092 -e MQ_TYPE=kafka -e MONGO_ENABLED=true -e LMDB_ENABLED=false --network flowcept_default flowcept /opt/conda/envs/flowcept/bin/pytest --ignore=tests/instrumentation_tests/ml_tests

# This command can be removed once we have our CLI
liveness:
	python -c 'from flowcept import Flowcept; print(Flowcept.services_alive())'

dev_agent:
	mcp dev src/flowcept/flowceptor/adapters/agents/flowcept_agent.py

install_dev_agent: # Run this to fix python env problems in the MCP studio env
	mcp install src/flowcept/flowceptor/adapters/agents/flowcept_agent.py


# Run services with Kafka using Docker
services-kafka:
	docker compose --file deployment/compose-kafka.yml up --detach

# Stop Kafka services and remove attached volumes
services-stop-kafka:
	docker compose --file deployment/compose-kafka.yml down --volumes

# Run services with Mofka using Docker
services-mofka:
	docker compose --file deployment/compose-mofka.yml up --detach

# Stop Mofka services and remove attached volumes
services-stop-mofka:
	docker compose --file deployment/compose-mofka.yml down --volumes

# Run unit tests using pytest
.PHONY: tests
tests:
	pytest --ignore=tests/adapters/test_tensorboard.py

.PHONY: tests-notebooks
tests-notebooks:
	pytest --nbmake "notebooks/" --nbmake-timeout=600 --ignore=notebooks/dask_from_CLI.ipynb --ignore=notebooks/tensorboard.ipynb
