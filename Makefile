# Show help, place this first so it runs with just `make`
help:
	@printf "\nCommands:\n"
	@printf "\033[32mbuild\033[0m           	build the Docker image\n"
	@printf "\033[32mrun\033[0m             	run the Docker container\n"
	@printf "\033[32mliveness\033[0m        	check if the services are alive\n"
	@printf "\033[32mservices\033[0m        	run services using Docker\n"
	@printf "\033[32mservices-stop\033[0m   	stop the running Docker services\n"
	@printf "\033[32mtests\033[0m           	run unit tests with pytest\n"
	@printf "\033[32mtests-in-container\033[0m 	run unit tests with pytest inside Flowcept's container\n"
	@printf "\033[32mtests-all\033[0m       	run all unit tests with pytest, including very long-running ones\n"
	@printf "\033[32mtests-notebooks\033[0m 	tests the notebooks, using pytest\n"
	@printf "\033[32mclean\033[0m           	remove cache directories and Sphinx build output\n"
	@printf "\033[32mdocs\033[0m            	build HTML documentation using Sphinx\n"
	@printf "\033[32mchecks\033[0m          	run ruff linter and formatter checks\n"
	@printf "\033[32mreformat\033[0m        	run ruff linter and formatter\n"

# Run linter and formatter checks using ruff
checks:
	ruff check src
	ruff format --check src

reformat:
	ruff check src
	ruff format src

# Remove cache directories and Sphinx build output
clean:
	rm -rf .ruff_cache
	rm -rf .pytest_cache
	rm -rf mnist_data
	rm -rf tensorboard_events
	rm -f docs_dump_tasks_*
	rm -f dump_test.json
	find . -type f -name "*.log" -exec rm -f {} \;
	find . -type f -name "*.pth" -exec rm -f {} \;
	find . -type f -name "mlflow.db" -exec rm -f {} \;
	find . -type d -name "mlruns" -exec rm -rf {} \;
	find . -type d -name "__pycache__" -exec rm -rf {} \;  2>/dev/null
	sphinx-build -M clean docs docs/_build

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

# Build a new Docker image for Flowcept
build:
	bash deployment/build-image.sh

run:
	docker run --rm -v $(shell pwd):/flowcept -e KVDB_HOST=flowcept_redis -e MQ_HOST=flowcept_redis -e MONGO_HOST=flowcept_mongo --network flowcept_default -it flowcept

tests-in-container:
	docker run --rm -v $(shell pwd):/flowcept -e KVDB_HOST=flowcept_redis -e MQ_HOST=flowcept_redis -e MONGO_HOST=flowcept_mongo --network flowcept_default flowcept /opt/conda/envs/flowcept/bin/pytest --ignore=tests/decorator_tests/ml_tests

# This command can be removed once we have our CLI
liveness:
	python -c 'from flowcept import Flowcept; print(Flowcept.services_alive())'

# Run unit tests using pytest
.PHONY: tests
tests:
	pytest --ignore=tests/decorator_tests/ml_tests/llm_tests

.PHONY: tests-notebooks
tests-notebooks:
	pytest --nbmake "notebooks/" --nbmake-timeout=600 --ignore=notebooks/dask_from_CLI.ipynb

.PHONY: tests-all
tests-all:
	pytest

