[![Documentation](https://img.shields.io/badge/docs-readthedocs.io-green.svg)](https://flowcept.readthedocs.io/)
[![Build](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml)
[![PyPI](https://badge.fury.io/py/flowcept.svg)](https://pypi.org/project/flowcept)
[![Tests](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml)
[![Code Formatting](https://github.com/ORNL/flowcept/actions/workflows/checks.yml/badge.svg?branch=dev)](https://github.com/ORNL/flowcept/actions/workflows/checks.yml)
[![License: MIT](https://img.shields.io/github/license/ORNL/flowcept)](LICENSE)

# Flowcept

Flowcept captures and queries workflow provenance at runtime with minimal code changes and low overhead. It unifies data from diverse tools and workflows across the Edge–Cloud–HPC continuum and provides ML-aware capture, telemetry, and flexible storage.

---

# Quickstart

This is the fastest way to see Flowcept capturing provenance from plain Python functions, no external services needed.

1) Install and initialize settings

```shell
# Make sure you activate your Python environment (e.g., conda, venv) first
pip install flowcept
flowcept --init-settings
```

2) Run the minimal example

Save as `quickstart.py` and run `python quickstart.py.`

```python
"""
A minimal example of Flowcept's instrumentation using @decorators.
This example needs no DB, broker, or external service.
"""
import json

from flowcept import Flowcept, flowcept_task
from flowcept.instrumentation.flowcept_decorator import flowcept


@flowcept_task(output_names="o1")
def sum_one(i1):
    return i1 + 1


@flowcept_task(output_names="o2")
def mult_two(o1):
    return o1 * 2


@flowcept
def main():
    n = 3
    o1 = sum_one(n)
    o2 = mult_two(o1)
    print("Final output", o2)


if __name__ == "__main__":
    main()

    prov_messages = Flowcept.read_messages_file()
    assert len(prov_messages) == 2
    print(json.dumps(prov_messages, indent=2))
```

You should see:
- Final output 8 printed to stdout, and
- Two provenance messages printed, each related to an executed function.

For online querying, telemetry, adapters (MLflow, Dask, TensorBoard), PyTorch instrumentation, HPC or federated runs,
and more, see the [Jupyter Notebooks](notebooks) and [Examples directory](examples) for utilization examples.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Setup and the Settings File](#setup)
- [Running with Containers](#running-with-containers)
- [Examples](#examples)
- [Data Persistence](#data-persistence)
- [Performance Tuning](#performance-tuning-for-performance-evaluation)
- [AMD GPU Setup](#install-amd-gpu-lib)
- [Further Documentation](#documentation)

## Overview

Flowcept captures and queries workflow provenance at runtime with minimal code changes and low data capture overhead,
unifying data from diverse tools and workflows.

Designed for scenarios involving critical data from multiple, federated workflows in the Edge-Cloud-HPC continuum, Flowcept supports end-to-end monitoring, analysis, querying, and enhanced support for Machine Learning (ML) workflows.

## Features

- Automatic workflow provenance capture with minimal intrusion
- Adapters for MLflow, Dask, TensorBoard; easy to add more
- Optional explicit instrumentation via decorators
- ML-aware capture, from workflow to epoch and layer granularity
- Low overhead, suitable for HPC and distributed setups
- Telemetry capture for CPU, GPU, memory, linked to dataflow
- Pluggable MQ and storage backends (Redis, Kafka, MongoDB, LMDB)
- [W3C PROV](https://www.w3.org/TR/prov-overview/) adherence 

Explore [Jupyter Notebooks](notebooks) and [Examples](examples) for usage.

## Installation

Flowcept can be installed in multiple ways, depending on your needs.

### 1. Default Installation
To install Flowcept with its basic dependencies from [PyPI](https://pypi.org/project/flowcept/), run:

```shell
pip install flowcept
```

This installs the core Flowcept package but does **not** include MongoDB, Redis, or any adapter-specific dependencies.

### 2. Installing Specific Adapters and Additional Dependencies
To install extra dependencies required for specific adapters or features (good practice is to install only what you need!):

```shell
pip install flowcept[mongo]         # Install Flowcept with MongoDB support.
pip install flowcept[mlflow]        # Install MLflow adapter.
pip install flowcept[dask]          # Install Dask adapter.
pip install flowcept[tensorboard]   # Install TensorBoard adapter.
pip install flowcept[kafka]         # Use Kafka as the MQ instead of Redis.
pip install flowcept[nvidia]        # Capture NVIDIA GPU runtime information.
pip install flowcept[analytics]     # Enable extra analytics features.
pip install flowcept[dev]           # Install Flowcept's developer dependencies.
```

### 3. Install All Optional Dependencies at Once

WARNING: Very likely you will not need this, as this will install several dependencies that won't make sense to be in
a same Python environment. This is useful for developers contributing to Flowcept's codebase, who may
need all dependencies installed. 

```
pip install flowcept[all]
```

### 4. Installing from Source
To install Flowcept from the source repository:

```
git clone https://github.com/ORNL/flowcept.git
cd flowcept
pip install .
```

You can also install specific dependencies using:

```
pip install .[dependency_name]
```

This follows the same pattern as step 2, allowing for a customized installation from source.

## Setup

### Start the MQ System:

To use Flowcept, one needs to start a MQ system `make services`. This will start up Redis but see other options in the [deployment](deployment) directory and see [Data Persistence](#data-persistence) notes below.

### Flowcept Settings File

Flowcept requires a settings file for configuration.

Running `flowcept --init-settings` will create a minimal settings file under your home directory: `~/.flowcept/setting.yaml`. 

You can find an example configuration file [here](resources/sample_settings.yaml), with documentation for each parameter provided as inline comments.

#### What You Can Configure:

- Message queue and database routes, ports, and paths;
- Buffer sizes and flush settings;
- Telemetry data capture settings;
- Instrumentation and PyTorch details;
- Log levels;
- Data observability adapters; and more.

#### How to use a custom settings file:

Create or modify your settings file based on the [example](resources/sample_settings.yaml).

Set the `FLOWCEPT_SETTINGS_PATH` environment variable to its absolute path:
```sh
export FLOWCEPT_SETTINGS_PATH=/absolute/path/to/your/settings.yaml
```

If this variable is not set, Flowcept will use the default values from the [example](resources/sample_settings.yaml) file.

# Running with Containers

To use containers instead of installing Flowcept's dependencies on your host system, we provide a [Dockerfile](deployment/Dockerfile) alongside a [docker-compose.yml](deployment/compose.yml) for dependent services (e.g., Redis, MongoDB).  

#### Notes:  
- As seen in the steps below, there are [Makefile](Makefile) commands to build and run the image. Please use them instead of running the Docker commands to build and run the image.
- The Dockerfile builds from a local `miniconda` image, which will be built first using the [build-image.sh](deployment/build-image.sh) script.  
- All dependencies for all adapters are installed, increasing build time. Edit the Dockerfile to customize dependencies based on our [pyproject.toml](pyproject.toml) to reduce build time if needed.  

#### Steps:

1. Build the Docker image:  
    ```bash
    make build
    ```

2. Start dependent services:
    ```bash
    make services
    ```

3. Run the image interactively:
    ```bash
    make run
    ```

4. Optionally, run Unit tests in the container:
    ```bash
    make tests-in-container
    ```
# Examples

### Adapters and Notebooks

 See the [Jupyter Notebooks](notebooks) and [Examples directory](examples) for utilization examples.

## Supported Adapters & Backends

| Category                           | Supported Options |
|------------------------------------|----------------------------------------------------------------------------------|
| **Data Observability**             | [MLflow](https://github.com/ORNL/flowcept/blob/main/examples/mlflow_example.py), [Dask](https://github.com/ORNL/flowcept/blob/main/examples/dask_example.py), [TensorBoard](https://github.com/ORNL/flowcept/blob/main/examples/tensorboard_example.py) |
| **Instrumentation and Decorators** | - [@flowcept](https://github.com/ORNL/flowcept/blob/main/examples/start_here.py): capture a bigger block of code as a workflow <br> - [@flowcept_task](https://github.com/ORNL/flowcept/blob/main/examples/instrumented_simple_example.py): generic tasks <br> - `@telemetry_flowcept_task`: same as `@flowcept_task`, but optimized for telemetry capture <br> - `@lightweight_flowcept_task`: same as `@flowcept_task`, but very lightweight, optimized for HPC workloads <br> - [Loop](https://github.com/ORNL/flowcept/blob/main/examples/instrumented_loop_example.py) <br> - [PyTorch Model](https://github.com/ORNL/flowcept/blob/main/examples/llm_complex/llm_model.py) <br> - [MCP Agents](https://github.com/ORNL/flowcept/blob/main/examples/agents/aec_agent_mock.py) |
| **Message Queues (MQ)**            | [Redis](https://redis.io), [Kafka](https://kafka.apache.org), [Mofka](https://mofka.readthedocs.io) <br> _Setup example:_ [docker compose](https://github.com/ORNL/flowcept/blob/main/deployment/compose.yml) |
| **Databases**                      | MongoDB, LMDB |

## Data Persistence

Flowcept uses an ephemeral message queue (MQ) with a pub/sub system to flush observed data. For optional data persistence, you can choose between:

- [LMDB](https://lmdb.readthedocs.io/) (default): A lightweight, file-based database requiring no external services (but note it might require `gcc`). Ideal for simple tests or cases needing basic data persistence without query capabilities. Data stored in LMDB can be loaded into tools like Pandas for complex analysis. Flowcept's database API provides methods to export data in LMDB into Pandas DataFrames.
- [MongoDB](https://www.mongodb.com/): A robust, service-based database with advanced query capabilities. Required to use Flowcept's Query API (i.e., `flowcept.Flowcept.db`) to run more complex queries and other features like ML model management or runtime queries (i.e., query while writing). To use MongoDB, initialize the service with `make services-mongo`.

Flowcept supports writing to both databases simultaneously (default configuration), individually, or to neither, depending on configuration.

If data persistence is disabled, captured data is sent to the MQ without any default consumer subscribing to persist it. In this case, querying the data requires creating a custom consumer to subscribe to the MQ.

However, for querying, Flowcept Database API uses only one at a time. If both are enabled, Flowcept defaults to MongoDB. If neither is enabled, an error will occur.

Data stored in MongoDB and LMDB are interchangeable. You can switch between them by transferring data from one to the other as needed.

## Performance Tuning for Performance Evaluation

In the settings.yaml file, many variables may impact interception efficiency. 
Please be mindful of the following parameters:

* `mq`
    - `buffer_size` and `insertion_buffer_time_secs`. -- `buffer_size: 1` is really bad for performance, but it will give the most up-to-date info possible to the MQ.
    
* `log`
    - set both stream and files to disable

* `telemetry_capture` 
  The more things you enable, the more overhead you'll get. For GPU, you can turn on/off specific metrics.

* `instrumentation`
  This will configure whether every single granular step in the model training process will be captured. Disable very granular model inspection and try to use more lightweight methods. There are commented instructions in the settings.yaml sample file.

Other thing to consider:

```
project:
  replace_non_json_serializable: false # Here it will assume that all captured data are JSON serializable
  db_flush_mode: offline               # This disables the feature of runtime analysis in the database.
mq:
  chunk_size: -1                       # This disables chunking the messages to be sent to the MQ. Use this only if the main memory of the compute notes is large enough.
```

Other variables depending on the adapter may impact too. For instance, in Dask, timestamp creation by workers add interception overhead. As we evolve the software, other variables that impact overhead appear and we might not stated them in this README file yet. If you are doing extensive performance evaluation experiments using this software, please reach out to us (e.g., create an issue in the repository) for hints on how to reduce the overhead of our software.

## Install AMD GPU Lib

This section is only important if you want to enable GPU runtime data capture and the GPU is from AMD. NVIDIA GPUs don't need this step.

For AMD GPUs, we rely on the official AMD ROCM library to capture GPU data.

Unfortunately, this library is not available as a pypi/conda package, so you must manually install it. See instructions in the link: https://rocm.docs.amd.com/projects/amdsmi/en/latest/

Here is a summary:

1. Install the AMD drivers on the machine (check if they are available already under `/opt/rocm-*`).
2. Suppose it is /opt/rocm-6.2.0. Then, make sure it has a share/amd_smi subdirectory and pyproject.toml or setup.py in it.
3. Copy the amd_smi to your home directory: `cp -r /opt/rocm-6.2.0/share/amd_smi ~`
4. cd ~/amd_smi
5. In your python environment, do a pip install .

Current code is compatible with this version: amdsmi==24.7.1+0012a68
Which was installed using Frontier's /opt/rocm-6.3.1/share/amd_smi

## Torch Dependencies

Some unit tests utilize `torch==2.2.2`, `torchtext=0.17.2`, and `torchvision==0.17.2`. They are only really needed to run some tests and will be installed if you run `pip install flowcept[ml_dev]` or `pip install flowcept[all]`. If you want to use Flowcept with Torch, please adapt torch dependencies according to your project's dependencies.

## Documentation

Full documentation is available on [Read the Docs](https://flowcept.readthedocs.io/).

## Cite us

If you used Flowcept in your research, consider citing our paper.

```
Towards Lightweight Data Integration using Multi-workflow Provenance and Data Observability
R. Souza, T. Skluzacek, S. Wilkinson, M. Ziatdinov, and R. da Silva
19th IEEE International Conference on e-Science, 2023.
```

**Bibtex:**

```latex
@inproceedings{souza2023towards,  
  author = {Souza, Renan and Skluzacek, Tyler J and Wilkinson, Sean R and Ziatdinov, Maxim and da Silva, Rafael Ferreira},
  booktitle = {IEEE International Conference on e-Science},
  doi = {10.1109/e-Science58273.2023.10254822},
  link = {https://doi.org/10.1109/e-Science58273.2023.10254822},
  pdf = {https://arxiv.org/pdf/2308.09004.pdf},
  title = {Towards Lightweight Data Integration using Multi-workflow Provenance and Data Observability},
  year = {2023}
}

```

## Disclaimer & Get in Touch

Refer to [Contributing](CONTRIBUTING.md) for adding new adapters or contributing with the codebase.

Please note that this a research software. We encourage you to give it a try and use it with your own stack.
We are continuously working on improving documentation and adding more examples and notebooks, but we are continuously improving documentation and examples. If you are interested in working with Flowcept in your own scientific project, we can give you a jump start if you reach out to us. Feel free to [create an issue](https://github.com/ORNL/flowcept/issues/new), [create a new discussion thread](https://github.com/ORNL/flowcept/discussions/new/choose) or drop us an email (we trust you'll find a way to reach out to us :wink:).

## Acknowledgement

This research uses resources of the Oak Ridge Leadership Computing Facility at the Oak Ridge National Laboratory, which is supported by the Office of Science of the U.S. Department of Energy under Contract No. DE-AC05-00OR22725.
