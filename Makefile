# Show help, place this first so it runs with just `make`
help:
	@printf "\nCommands:\n"
	@printf "\033[32mchecks\033[0m          run ruff linter and formatter checks\n"
	@printf "\033[32mclean\033[0m           remove cache directories and Sphinx build output\n"
	@printf "\033[32mdocs\033[0m            build HTML documentation using Sphinx\n"
	@printf "\033[32mservices\033[0m        run services using Docker\n"
	@printf "\033[32mservices-stop\033[0m   stop the running Docker services\n"
	@printf "\033[32mtests\033[0m           run unit tests with pytest\n"


# Run linter and formatter checks using ruff
checks:
	ruff check src
	ruff format --check src

# Remove cache directories and Sphinx build output
clean:
	rm -rf .ruff_cache
	rm -rf .pytest_cache
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

# Run unit tests using pytest
tests:
	pytest --ignore=tests/decorator_tests/ml_tests/llm_tests
