[![Build](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml)
[![PyPI](https://badge.fury.io/py/flowcept.svg)](https://pypi.org/project/flowcept)
[![Tests](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml)
[![Code Formatting](https://github.com/ORNL/flowcept/actions/workflows/checks.yml/badge.svg?branch=dev)](https://github.com/ORNL/flowcept/actions/workflows/checks.yml)
[![License: MIT](https://img.shields.io/github/license/ORNL/flowcept)](LICENSE)

# Flowcept

Flowcept is a runtime data integration system that captures and queries workflow provenance with minimal or no code changes. It unifies data across diverse workflows and tools, enabling integrated analysis and insights, especially in federated environments. Designed for scenarios involving critical data from multiple workflows, Flowcept seamlessly integrates data at runtime, providing a unified view for end-to-end monitoring and analysis, and enhanced support for Machine Learning (ML) workflows.

Other capabilities include:

- Automatic multi-workflow provenance data capture;
- Data observability, enabling minimal intrusion to user workflows;
- Explicit user workflow instrumentation, if this is preferred over implicit data observability;
- ML data capture in various levels of details: workflow, model fitting or evaluation task, epoch iteration, layer forwarding;
- ML model management;
- Adapter-based, loosely-coupled system architecture, making it easy to plug and play with different data processing systems and backend database (e.g., MongoDB) or MQ services (e.g., Redis, Kafka);
- Low-overhead focused system architecture, to avoid adding performance overhead particularly to workloads that run on HPC machines;
- Telemetry data capture (e.g., CPU, GPU, Memory consumption) linked to the application dataflow;
- Highly customizable to multiple use cases, enabling easy toggle between settings (e.g., with/without provenance capture; with/without telemetry and which telemetry type to capture; which adapters or backend services to run with); 
- [W3C PROV](https://www.w3.org/TR/prov-overview/) adherence;
 
Notes:

- Currently implemented data observability adapters:
  - MLFlow
  - Dask
  - TensorBoard
- Python scripts can be easily instrumented via `@decorators` using `@flowcept_task` (for generic Python method) or `@torch_task` (for methods that encapsulate PyTorch model manipulation, such as training or evaluation). 
- Currently supported MQ systems:
  - Kafka
  - Redis
- Currently supported database systems:
  - MongoDB
  - Lightning Memory-Mapped Database (lightweight file-only database system)

Explore [Jupyter Notebooks](notebooks) and [Examples](examples) for usage.

Refer to [Contributing](CONTRIBUTING.md) for adding new adapters. Note: The term "plugin" in the codebase is synonymous with "adapter," and future updates will standardize terminology.

# Installation

Flowcept can be installed in multiple ways, depending on your needs.

### 1. Default Installation
To install Flowcept with its basic dependencies from [PyPI](https://pypi.org/project/flowcept/), run:

```
pip install flowcept
```

This installs the core Flowcept package but does **not** include MongoDB or any adapter-specific dependencies.



### 2. Installing Specific Adapters and Additional Dependencies
To install extra dependencies required for specific adapters or features, use:

```
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
If you want to install all optional dependencies, use:

```
pip install flowcept[all]
```

This is a convenient way to ensure all adapters are available, but it may install dependencies you don't need.

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

# Setup

### Start the MQ System:

To use Flowcept, one needs to start a MQ system `$> make services`. This will start up Redis but see other options in the [deployment](deployment) directory and see [Data Persistence](#data-persistence) notes below.

### Flowcept Settings File

Flowcept requires a settings file for configuration. You can find an example [here](resources/sample_settings.yaml).

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


### Simple Example with Decorators Instrumentation

In addition to existing adapters to Dask, MLFlow, and others (it's extensible for any system that generates data), Flowcept also offers instrumentation via @decorators. 

```python 
from flowcept import Flowcept, flowcept_task

@flowcept_task
def sum_one(n):
    return n + 1


@flowcept_task
def mult_two(n):
    return n * 2


with Flowcept(workflow_name='test_workflow'):
    n = 3
    o1 = sum_one(n)
    o2 = mult_two(o1)
    print(o2)

print(Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id}))
```

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

Please note that this a research software. We encourage you to give it a try and use it with your own stack. We are continuously working on improving documentation and adding more examples and notebooks, but we are continuously improving documentation and examples. If you are interested in working with Flowcept in your own scientific project, we can give you a jump start if you reach out to us. Feel free to [create an issue](https://github.com/ORNL/flowcept/issues/new), [create a new discussion thread](https://github.com/ORNL/flowcept/discussions/new/choose) or drop us an email (we trust you'll find a way to reach out to us :wink:).

## Acknowledgement

This research uses resources of the Oak Ridge Leadership Computing Facility at the Oak Ridge National Laboratory, which is supported by the Office of Science of the U.S. Department of Energy under Contract No. DE-AC05-00OR22725.
