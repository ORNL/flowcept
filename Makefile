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
	rm -rf .ruff_cache || true
	rm -rf .pytest_cache || true
	rm -rf mnist_data || true
	rm -rf tensorboard_events || true
	rm -f docs_dump_tasks_* || true
	rm -f dump_test.json || true
	find . -type d -name "*flowcept_lmdb*" -exec rm -rf {} \; || true
	find . -type f -name "*.log" -exec rm -f {} \; || true
	find . -type f -name "*.pth" -exec rm -f {} \; || true
	find . -type f -name "mlflow.db" -exec rm -f {} \; || true
	find . -type d -name "mlruns" -exec rm -rf {} \; 2>/dev/null || true
	find . -type d -name "__pycache__" -exec rm -rf {} \;  2>/dev/null || true
	find . -type d -name "*tfevents*" -exec rm -rf {} \;  2>/dev/null || true
	find . -type d -name "*output_data*" -exec rm -rf {} \;  2>/dev/null || true
	find . -type f -name "*nohup*" -exec rm -rf {} \;  2>/dev/null || true
	sphinx-build -M clean docs docs/_build > /dev/null 2>&1 || true

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

# Run unit tests using pytest
.PHONY: tests
tests:
	pytest

.PHONY: tests-notebooks
tests-notebooks:
	pytest --nbmake "notebooks/" --nbmake-timeout=600 --ignore=notebooks/dask_from_CLI.ipynb
