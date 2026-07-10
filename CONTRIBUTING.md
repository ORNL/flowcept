# Contributing

Welcome to the Flowcept project! To make sure new contributions align well with the project, following there are some guidelines to help you create code that fits right in. Following them increases the chances of your contributions being merged smoothly.

## Code Linting and Formatting

All Python code in the Flowcept package should adhere to the [PEP 8](https://peps.python.org/pep-0008/) style guide. Linting and formatting are handled through the project Makefile, which wraps [Ruff](https://github.com/astral-sh/ruff). Configuration for Ruff is defined in the [pyproject.toml](./pyproject.toml) file.

```text
make reformat
make checks
```

## Documentation

[Sphinx](https://www.sphinx-doc.org) along with the [Furo theme](https://github.com/pradyunsg/furo) are used to generate documentation for the project. The **docs** optional dependencies are needed to build the documentation on your local machine. Sphinx uses docstrings from the source code to build the API documentation. These docstrings should adhere to the [NumPy docstring conventions](https://numpydoc.readthedocs.io/en/latest/format.html). The commands shown below will build the documentation using Sphinx:

```text
cd docs
make html
```

## Branches and Pull Requests

There are two protected branches in this project: `dev` and `main`. This means that these two branches should be as stable as possible, especially the `main` branch. PRs to them should be peer-reviewed.

The `main` branch always has the latest working version of Flowcept, with a tagged release published to [PyPI](https://pypi.org/project/flowcept).

The `dev` branch may be ahead of `main` while new features are being implemented. Feature branches should be pull requested to the `dev` branch. Pull requests into the `main` branch should always be made from the `dev` branch and be merged when the developers agree it is time to do so.

## Issue Labels

When a new issue is created a priority label should be added indicating how important the issue is.

* `priority:low` - syntactic sugar, or addressing small amounts of technical debt or non-essential features
* `priority:medium` - is important to the completion of the milestone but does not require immediate attention
* `priority:high` - is essential to the completion of a milestone

## CI/CD Pipeline

### Automated versioning and releases

Flowcept follows semantic versioning. The [release workflow](.github/workflows/create-release-n-publish.yml) runs on pushes to `main`, creates a tagged release, and publishes the package to [PyPI](https://pypi.org/project/flowcept).

### Automated tests and code format check

Several GitHub Actions cover different runtime environments:

* [checks.yml](.github/workflows/checks.yml) runs code and documentation checks.
* [run-tests.yml](.github/workflows/run-tests.yml) runs the main test matrix, including Redis and Kafka paths.
* [run-tests-simple.yml](.github/workflows/run-tests-simple.yml) runs tests without MongoDB.
* [run-tests-offline.yml](.github/workflows/run-tests-offline.yml) runs the full-offline profile.
* [run-tests-kafka-and-rabbit-mq.yml](.github/workflows/run-tests-kafka-and-rabbit-mq.yml) runs Mongo-backed tests with Kafka and RabbitMQ.
* [run-tests-all-dbs.yml](.github/workflows/run-tests-all-dbs.yml) runs Mongo and non-Mongo database paths.
* [run-tests-in-container.yml](.github/workflows/run-tests-in-container.yml) runs tests inside the Flowcept container.
* [run-tests-py313.yml](.github/workflows/run-tests-py313.yml) runs the Python 3.13-compatible subset.
* [run-llm-tests.yml](.github/workflows/run-llm-tests.yml) runs the LLM/Dask example tests.

The main test workflows also run on the daily schedule configured in the workflow files.

## Checklist for Creating a new Flowcept adapter

1. Create a new package directory under `flowcept/flowceptor/adapters`
2. Create a new class that inherits from `BaseInterceptor`, and consider implementing the abstract methods:
    - Observe
    - Intercept
    - Callback
    - Prepare_task_msg

See the existing adapters for a reference.

3. [Optional] You may need extra classes, such as local state manager (we provide a generic [`Interceptor State Manager`](flowcept/flowceptor/adapters/interceptor_state_manager.py)), `@dataclasses`, Data Access Objects (`DAOs`), and event handlers.
4. Create a new entry in the [sample_settings.yaml](resources/sample_settings.yaml) file and in the [Settings factory](flowcept/commons/settings_factory.py)
5. Create a new entry in the [pyproject.toml](./pyproject.toml) file under the `[project.optional-dependencies]` section and adjust the rest of the file accordingly.
6. [Optional] Add a new constant to [vocabulary.py](flowcept/commons/vocabulary.py).
7. [Optional] Adjust flowcept.__init__.py.
