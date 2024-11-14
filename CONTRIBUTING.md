# Contributing

Welcome to the FlowCept project! To make sure new contributions align well with the project, following there are some guidelines to help you create code that fits right in. Following them increases the chances of your contributions being merged smoothly.

## Code Linting and Formatting

All Python code in the FlowCept package should adhere to the [PEP 8](https://peps.python.org/pep-0008/) style guide. All linting and formatting checks should be performed with [Ruff](https://github.com/astral-sh/ruff). Configuration for Ruff is defined in the [pyproject.toml](./pyproject.toml) file. The commands shown below will run the Ruff linter and formatter checks on the source directory:

```text
ruff check src
ruff format --check src
```

## Documentation

[Sphinx](https://www.sphinx-doc.org) along with the [Furo theme](https://github.com/pradyunsg/furo) are used to generate documentation for the project. The **docs** optional dependencies are needed to build the documentation on your local machine. Sphinx uses docstrings from the source code to build the API documentation. These docstrings should adhere to the [NumPy docstring conventions](https://numpydoc.readthedocs.io/en/latest/format.html). The commands shown below will build the documentation using Sphinx:

```text
cd docs
make html
```

## Branches and Pull Requests

There are two protected branches in this project: `dev` and `main`. This means that these two branches should be as stable as possible, especially the `main` branch. PRs to them should be peer-reviewed.

The `main` branch always has the latest working version of FlowCept, with a tagged release published to [PyPI](https://pypi.org/project/flowcept).

The `dev` branch may be ahead of `main` while new features are being implemented. Feature branches should be pull requested to the `dev` branch. Pull requests into the `main` branch should always be made from the `dev` branch and be merged when the developers agree it is time to do so.

## Issue Labels

When a new issue is created a priority label should be added indicating how important the issue is.

* `priority:low` - syntactic sugar, or addressing small amounts of technical debt or non-essential features
* `priority:medium` - is important to the completion of the milestone but does not require immediate attention
* `priority:high` - is essential to the completion of a milestone

## CI/CD Pipeline

### Automated versioning

FlowCept follows semantic versioning. There is a [GitHub Action](.github/workflows/create-release-n-publish.yml) that automatically bumps the patch number of the version at PRs to the main branch and uploads the package to PyPI.

### Automated tests and code format check

All human-triggered commits to any branch will launch the [automated tests GitHub Action](.github/workflows/run-tests.yml). PRs into `dev` or `main` will also trigger the [code linter and formatter checks](.github/workflows/run-checks.yml), using Ruff.

### Automated releases

All commits to the `main` branch will launch the [automated publish and release GitHub Action](.github/workflows/create-release-n-publish.yml). This will create a [tagged release](https://github.com/ORNL/flowcept/releases) and publish the package to [PyPI](https://pypi.org/project/flowcept).

## Checklist for Creating a new FlowCept adapter

1. Create a new package directory under `flowcept/flowceptor/plugins`
2. Create a new class that inherits from `BaseInterceptor`, and consider implementing the abstract methods:
    - Observe
    - Intercept
    - Callback
    - Prepare_task_msg

See the existing plugins for a reference.

3. [Optional] You may need extra classes, such as local state manager (we provide a generic [`Interceptor State Manager`](flowcept/flowceptor/adapters/interceptor_state_manager.py)), `@dataclasses`, Data Access Objects (`DAOs`), and event handlers.
4. Create a new entry in the [settings.yaml](resources/settings.yaml) file and in the [Settings factory](flowcept/commons/settings_factory.py)
5. Create a new entry in the [pyproject.toml](./pyproject.toml) file under the `[project.optional-dependencies]` section and adjust the rest of the file accordingly.
6. [Optional] Add a new constant to [vocabulary.py](flowcept/commons/vocabulary.py).
7. [Optional] Adjust flowcept.__init__.py.
