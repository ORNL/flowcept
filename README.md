[![Build](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml)
[![PyPI](https://badge.fury.io/py/flowcept.svg)](https://pypi.org/project/flowcept)
[![Unit Tests](https://github.com/ORNL/flowcept/actions/workflows/run-unit-tests.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/run-unit-tests.yml)
[![Code Formatting](https://github.com/ORNL/flowcept/actions/workflows/code-formatting.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/code-formatting.yml)
[![License: MIT](https://img.shields.io/github/license/ORNL/flowcept)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# Flowcept

## Development Environment

### Code Formatting

Flowcept code uses [Black](https://github.com/psf/black), a PEP 8 compliant code formatter, and 
[Flake8](https://github.com/pycqa/flake8), a code style guide enforcement tool. To install the
these tools you simply need to run the following:

```bash
$ pip install flake8 black
```

Before _every commit_, you should run the following:

```bash
$ black .
$ flake8 .
```

If errors are reported by `flake8`, please fix them before commiting the code.

### Running Tests

There are a few dependencies that need to be installed to run the pytest, if you installed the requirements.txt file then this should be covered as well.
```bash
$ pip install pytest
```

From the root directory using pytest we can run:

```bash
$ pytest
```

## Redis for local interceptions
```bash
$ docker run -p 6379:6379  --name redis -d redis
```

## RabbitMQ for Zambeze plugin
```bash
$ docker run -it --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3.11-management
```
