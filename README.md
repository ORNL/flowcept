<p align="center">
  <picture>
    <img src="./docs/img/flowcept-logo.png" alt="Flowcept Logo" width="200"/>
  </picture>
</p>
<h3 align="center">Lightweight Distributed Workflow Provenance</h3>



---

Flowcept captures and queries workflow provenance at runtime with minimal code changes and low overhead. It unifies data from diverse tools and workflows across the Edge–Cloud–HPC continuum and provides ML-aware capture, MCP agents provenance, telemetry, extensible adapters, and flexible storage.

---

[![Documentation](https://img.shields.io/badge/docs-readthedocs.io-green.svg)](https://flowcept.readthedocs.io/)
[![Build](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml)
[![PyPI](https://badge.fury.io/py/flowcept.svg)](https://pypi.org/project/flowcept)
[![Tests](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml)
[![Code Formatting](https://github.com/ORNL/flowcept/actions/workflows/checks.yml/badge.svg?branch=dev)](https://github.com/ORNL/flowcept/actions/workflows/checks.yml)
[![License: MIT](https://img.shields.io/github/license/ORNL/flowcept)](LICENSE)

---

# Quickstart

The easiest way to capture provenance from plain Python functions, with no external services needed:

1) Install and initialize settings

```shell
# Make sure you activate your Python environment (e.g., conda, venv) first
pip install flowcept
flowcept --init-settings
```
This generates a minimal settings file in `~/.flowcept/settings.yaml.`

2) Run the minimal example

Save the following script as `quickstart.py` and run `python quickstart.py.`

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

This creates a provenance file in `flowcept_messages.jsonl`.  In it, you will see two provenance messages, each related to an executed function.

```json
[
  {
    "activity_id": "sum_one",
    "workflow_id": "fe546706-ef46-4482-8f70-3af664a7131b",
    "campaign_id": "76088532-3bef-4343-831e-d8a5d9156174",
    "used": {
      "i1": 3
    },
    "started_at": 1757171258.637908,
    "hostname": "my_laptop",
    "task_id": "1757171258.637908",
    "status": "FINISHED",
    "ended_at": 1757171258.6379142,
    "generated": {
      "o1": 4
    },
    "type": "task"
  },
  {
    "activity_id": "mult_two",
    "workflow_id": "fe546706-ef46-4482-8f70-3af664a7131b",
    "campaign_id": "76088532-3bef-4343-831e-d8a5d9156174",
    "used": {
      "o1": 4
    },
    "started_at": 1757171258.637933,
    "hostname": "my_laptop",
    "task_id": "1757171258.637933",
    "status": "FINISHED",
    "ended_at": 1757171258.6379352,
    "generated": {
      "o2": 8
    },
    "type": "task"
  }
]
```


For online querying using databases, MCP agents and Grafana, telemetry, adapters (MLflow, Dask, TensorBoard), PyTorch and MCP instrumentation, HPC optimization or federated runs,
and more, see the [Jupyter Notebooks](notebooks), the [Examples directory](examples) and the [complete documentation](https://flowcept.readthedocs.io/).

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

Designed for scenarios involving critical data from multiple, federated workflows in the Edge-Cloud-HPC continuum, Flowcept supports end-to-end monitoring, analysis, querying, and enhanced support for Machine Learning (ML) and for agentic workflows.

## Features

- Automatic workflow provenance capture with minimal intrusion
- Adapters for MLflow, Dask, TensorBoard; easy to add more
- Optional explicit instrumentation via decorators
- ML-aware capture, from workflow to epoch and layer granularity
- Agentic workflows: MCP agents-aware provenance capture
- Low overhead, suitable for HPC and highly distributed setups
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

This installs the minimal Flowcept package, **not** including MongoDB, Redis, MCP, or any adapter-specific dependencies.

### 2. Installing Specific Adapters and Additional Dependencies

Flowcept integrates with several tools and services, but you should **only install what you actually need**.  
Good practice is to cherry-pick the extras relevant to your workflow instead of installing them all.

```shell
pip install flowcept[mongo]         # MongoDB support
pip install flowcept[mlflow]        # MLflow adapter
pip install flowcept[dask]          # Dask adapter
pip install flowcept[tensorboard]   # TensorBoard adapter
pip install flowcept[kafka]         # Kafka message queue
pip install flowcept[nvidia]        # NVIDIA GPU runtime capture
pip install flowcept[telemetry]     # CPU/GPU/memory telemetry capture
pip install flowcept[lmdb]          # LMDB lightweight database
pip install flowcept[mqtt]          # MQTT support
pip install flowcept[llm_agent]     # MCP agent, LangChain, Streamlit integration: needed either for MCP capture or for the Flowcept Agent.
pip install flowcept[llm_google]    # Google GenAI + Flowcept agent support
pip install flowcept[analytics]     # Extra analytics (seaborn, plotly, scipy)
pip install flowcept[dev]           # Developer dependencies (docs, tests, lint, etc.)
```

### 3. Installing with Common Runtime Bundle

```shell
pip install flowcept[extras]
```

The `extras` group is a convenience shortcut that bundles the most common runtime dependencies.  
It is intended for users who want a fairly complete, but not maximal, Flowcept environment.

You might choose `flowcept[extras]` if:

- You want Flowcept to run out-of-the-box with Redis, telemetry, and MongoDB.  
- You prefer not to install each extra one by one

⚠️ If you only need one of these features, install it individually instead of `extras`.

### 4. Install All Optional Dependencies at Once

Flowcept provides a combined all extra, but installing everything into a single environment is not recommended for users.
Many of these dependencies are unrelated and should not be mixed in the same runtime. This option is only intended for Flowcept developers who need to test across all adapters and integrations.

```
pip install flowcept[all]
```

### 5. Installing from Source
To install Flowcept from the source repository:

```
git clone https://github.com/ORNL/flowcept.git
cd flowcept
pip install .
```

You can then install specific dependencies similarly as above:

```
pip install .[optional_dependency_name]
```

This follows the same pattern as step 2, allowing for a customized installation from source.

## Setup

The [Quickstart](#quickstart) example works with just `pip install flowcept`, no extra setup is required.

For online queries or distributed capture, Flowcept relies on two optional components:

- **Message Queue (MQ)** — message broker / pub-sub / data stream  
- **Database (DB)** — persistent storage for historical queries  

---

#### Message Queue (MQ)

- Required for anything beyond Quickstart  
- Flowcept publishes provenance data to the MQ during workflow runs  
- Developers can subscribe with custom consumers (see [this example](examples/consumers/simple_consumer.py).  
- You can monitor or print messages in motion using `flowcept --stream-messages --print`.  

Supported MQs:
- [Redis](https://redis.io) → **default**, lightweight, works on Linux, macOS, Windows, and HPC (tested on [Frontier](link) and [Summit](link))  
- [Kafka](https://kafka.apache.org) → for distributed environments or if Kafka is already in your stack  
- [Mofka](https://mofka.readthedocs.io) → optimized for HPC runs  

---

#### Database (DB)

- **Optional**, but required for:
  - Persisting provenance beyond MQ memory/disk buffers  
  - Running complex analytical queries on historical data  

Supported DBs:
- [MongoDB](https://www.mongodb.com) → default, efficient bulk writes + rich query support  
- [LMDB](https://lmdb.readthedocs.io) → lightweight, no external service, basic query capabilities  

---

### Notes

- Without a DB:
  - Provenance remains in the MQ only (persistence not guaranteed)  
  - Complex historical queries are unavailable  
- Flowcept’s architecture is modular: other MQs and DBs (graph, relational, etc.) can be added in the future  
- Deployment examples for MQ and DB are provided in the [deployment](deployment) directory  
 

### Downloading and Starting External Services (MQ or DB)

Flowcept uses external services for message queues (MQ) and databases (DB). You can start them with Docker Compose, plain containers, or directly on your host.

---

#### Using Docker Compose (recommended)

We provide a [Makefile](deployment/Makefile) with shortcuts:

1. **Redis only (no DB)**: `make services`   (LMDB can be used in this setup as a lightweight DB)
2. **Redis + MongoDB**: `make services-mongo`
3. **Kafka + MongoDB**: `make services-kafka`
4. **Mofka only (no DB)**: `make services-mofka`

To customize, edit the YAML files in [deployment](deployment/) and run `docker compose -f deployment/<compose-file>.yml up -d`

---

#### Using Docker (without Compose)

See the [deployment/](deployment/) compose files for expected images and configurations. You can adapt them to your environment and use standard `docker pull / run / exec` commands.

---

#### Running on the Host (no containers)

1. Install binaries for the service you need:  
   - **macOS** users can install with [Homebrew](https://brew.sh).  
     Example for Redis:
     ```bash
     brew install redis
     brew services start redis
     ```

   - On Linux, use your distro package manager (e.g. `apt`, `dnf`, `yum`) 
   - If non-root (typically the case if you want to deploy these services locally in an HPC system), search for the installed binaries for your OS/hardware architecture, download them in a directory that you have r+w permission, and run them.
   - On Windows, utilize [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) to use a Linux distro.

2. Start services normally (`redis-server`, `mongod`, `kafka-server-start.sh`, etc.).

## Flowcept Settings File

Flowcept uses a settings file for configuration.

- To create a minimal settings file (**recommended**), run: `flowcept --init-settings` → creates `~/.flowcept/settings.yaml`

- To create a full settings file with all options, run: `flowcept --init-settings --full` → creates `~/.flowcept/settings.yaml`

---

#### What You Can Configure

- Message queue and database routes, ports, and paths  
- MCP agent ports and LLM API keys  
- Buffer sizes and flush settings  
- Telemetry capture settings  
- Instrumentation and PyTorch details  
- Log levels  
- Data observability adapters  
- And more (see [example file](resources/sample_settings.yaml))  

---

#### Custom Settings File

Flowcept looks for its settings in the following order:

1. `~/.flowcept/settings.yaml` — created by running `flowcept --init-settings`  
2. Environment variable `FLOWCEPT_SETTINGS_PATH` — if set, Flowcept will use this environment variable  
3. [Default sample file](resources/sample_settings.yaml) — used if neither of the above is found

# Examples

### Adapters and Notebooks

 See the [Jupyter Notebooks](notebooks) and [Examples directory](examples) for utilization examples.

# Summary: Observability, Instrumentation, MQs, DBs, and Querying

| Category                           | Supported Options                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
|------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Data Observability Adapters**    | [MLflow](https://github.com/ORNL/flowcept/blob/main/examples/mlflow_example.py), [Dask](https://github.com/ORNL/flowcept/blob/main/examples/dask_example.py), [TensorBoard](https://github.com/ORNL/flowcept/blob/main/examples/tensorboard_example.py)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Instrumentation and Decorators** | - [@flowcept](https://github.com/ORNL/flowcept/blob/main/examples/start_here.py): encapsulate a function (e.g., a main function) as a workflow. <br> - [@flowcept_task](https://github.com/ORNL/flowcept/blob/main/examples/instrumented_simple_example.py): encapsulate a function as a task. <br> - `@telemetry_flowcept_task`: same as `@flowcept_task`, but optimized for telemetry capture. <br> - `@lightweight_flowcept_task`: same as `@flowcept_task`, but very lightweight, optimized for HPC workloads <br> - [Loop](https://github.com/ORNL/flowcept/blob/main/examples/instrumented_loop_example.py) <br> - [PyTorch Model](https://github.com/ORNL/flowcept/blob/main/examples/llm_complex/llm_model.py) <br> - [MCP Agent](https://github.com/ORNL/flowcept/blob/main/examples/agents/aec_agent_mock.py) |
| **Context Manager**                | `with Flowcept():` <br/> &nbsp;&nbsp;&nbsp;`# Workflow code` <br/><br/>Similar to the `@flowcept` decorator, but more flexible for instrumenting code blocks that aren’t encapsulated in a single function and for workflows with scattered code across multiple files.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Custom Task Creation**           | `FlowceptTask(activity_id=<id>, used=<inputs>, generated=<outputs>, ...)` <br/><br/>Use for fully customizable task instrumentation. Publishes directly to the MQ either via context management (`with FlowceptTask(...)`) or by calling `send()`. It needs to have a `Flowcept().start()` first (or within a `with Flowcept()` context). See [example](examples/consumers/ping_pong_example.py).                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **Message Queues (MQ)**            | - **Disabled** (offline mode: provenance events stay in an in-memory buffer, not accessible to external processes) <br> - [Redis](https://redis.io) → default, lightweight, easy to run anywhere <br> - [Kafka](https://kafka.apache.org) → for distributed, production setups <br> - [Mofka](https://mofka.readthedocs.io) → optimized for HPC runs <br><br> _Setup example:_ [docker compose](https://github.com/ORNL/flowcept/blob/main/deployment/compose.yml)                                                                                                                                                                                                                                                                                                                                                      |
| **Databases**                      | - **Disabled** → Flowcept runs in ephemeral mode (data only in MQ, no persistence) <br> - **[MongoDB](https://www.mongodb.com)** → default, rich queries and efficient bulk writes <br> - **[LMDB](https://lmdb.readthedocs.io)** → lightweight, file-based, no external service, basic query support                                                                                                                                                                                                                                                                                                                                                     |
| **Querying and Monitoring**        | - **[Grafana](deployment/compose-grafana.yml)** → dashboarding via MongoDB connector <br> - **MCP Flowcept Agent** → LLM-based querying of provenance data                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | 
| **Custom Consumer**                | You can implement your own consumer to monitor or query the provenance stream in real time. Useful for custom analytics, monitoring, debugging, or to persist the data in a different data model (e.g., graph) . See [example](examples/consumers/simple_consumer.py).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |


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
