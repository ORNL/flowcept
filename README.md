[![Build][build-badge]][build-link]
[![PyPI][pypi-badge]][pypi-link]
[![License: MIT][license-badge]](LICENSE)
[![Docs][docs-badge]][docs-link]
[![codecov][codecov-badge]][codecov-link]
[![Codacy Badge][codacy-badge]][codacy-link]
[![CodeFactor][codefactor-badge]][codefactor-link]
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# Flowcept

## Development Environment

### Code Formatting

Zambeze's code uses [Black](https://github.com/psf/black), a PEP 8 compliant code formatter, and 
[Flake8](https://github.com/pycqa/flake8), a code style guide enforcement tool. To install the
these tools you simply need to run the following:

```bash
pip install flake8 black
```

Before _every commit_, you should run the following:

```bash
black .
flake8 .
```

If errors are reported by `flake8`, please fix them before commiting the code.

### Running Tests

There are a few dependencies that need to be installed to run the pytest, if you installed the requirements.txt file then this should be covered as well.
```bash
pip install pytest
```

From the root directory using pytest we can run:

```bash
pytest
```

## Redis for local interceptions
```$ docker run -p 6379:6379  --name redis -d redis```

## RabbitMQ for Zambeze plugin
```$ docker run -it --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3.11-management```


[build-badge]:         https://github.com/ORNL/flowcept/workflows/Build/badge.svg
[build-link]:          https://github.com/ORNL/flowcept/actions
[license-badge]:       https://img.shields.io/github/license/ORNL/flowcept
[docs-badge]:          https://readthedocs.org/projects/flowcept/badge/?version=latest
[docs-link]:           https://flowcept.readthedocs.io/en/latest/
[pypi-badge]:          https://badge.fury.io/py/flowcept.svg
[pypi-link]:           https://pypi.org/project/flowcept/
[codecov-badge]:       https://codecov.io/gh/ORNL/flowcept/branch/main/graph/badge.svg?token=H5VS82WTRZ
[codecov-link]:        https://codecov.io/gh/ORNL/flowcept
[codefactor-badge]:    https://www.codefactor.io/repository/github/ornl/flowcept/badge
[codefactor-link]:     https://www.codefactor.io/repository/github/ornl/flowcept
