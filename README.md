[![Build](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml)
[![PyPI](https://badge.fury.io/py/flowcept.svg)](https://pypi.org/project/flowcept)
[![Tests](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml)
[![Code Formatting](https://github.com/ORNL/flowcept/actions/workflows/run-checks.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/run-checks.yml)
[![License: MIT](https://img.shields.io/github/license/ORNL/flowcept)](LICENSE)

# FlowCept

FlowCept is a runtime data integration system that enables any data processing system to capture and query workflow provenance with minimal or no code changes. It integrates data across workflows, providing insights into complex, large-scale, and heterogeneous data in federated environments. It has additional features if there are Machine Learning (ML) workflows involved. 

FlowCept is designed for scenarios where multiple workflows generate critical data requiring integrated analysis. These workflows may use diverse tools (e.g., provenance capture, databases, performance profiling, ML frameworks) or run on different data processing systems. FlowCept’s key capability is to seamlessly integrate data using observability, creating a unified data view at runtime for end-to-end analysis and monitoring.

Other capabilities include:

- Automatic multi-workflow provenance data capture;
- Data observability, enabling minimal intrusion to user workflows;
- Explicit user workflow instrumentation, if this is preferred over data observability;
- ML data capture in various levels of details: workflow, model fitting or evaluation task, epoch iteration, layer forwarding;
- ML model management;
- Adapter-based system architecture, making it easy to plug and play with different data processing systems and backend database (e.g., MongoDB) or MQ services (e.g., Redis, Kafka);
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

## Install and Setup:

1. Install FlowCept: 

`pip install .[all]` in this directory (or `pip install flowcept[all]`) if you want to install all dependencies.

For convenience, this will install all dependencies for all adapters. But it can install dependencies for adapters you will not use. For this reason, you may want to install like this: `pip install .[adapter_key1,adapter_key2]` for the adapters we have implemented, e.g., `pip install .[dask]`.
Currently, the optional dependencies available are:

```
pip install flowcept[mlflow]        # To install mlflow's adapter.
pip install flowcept[dask]          # To install dask's adapter.
pip install flowcept[tensorboard]   # To install tensorboaard's adapter.
pip install flowcept[kafka]         # To utilize Kafka as the MQ, instead of Redis.
pip install flowcept[nvidia]        # To capture NVIDIA GPU runtime information.
pip install flowcept[analytics]     # For extra analytics features.
pip install flowcept[dev]           # To install dev dependencies.
```

You do not need to install any optional dependency to run Flowcept without any adapter, e.g., if you want to use simple instrumentation (see below). In this case, you need to remove the adapter part from the [settings.yaml](resources/settings.yaml) file.
 
2. Start the Database and MQ System:

To use FlowCept, one needs to start a database and a MQ system. Currently, FlowCept supports MongoDB as its database and it supports both Redis and Kafka as the MQ system.

For convenience, the default needed services can be started using a [docker-compose file](deployment/compose.yml) deployment file. You can start them using `$> docker-compose -f deployment/compose.yml up`.

3. Optionally, define custom settings (e.g., routes and ports) accordingly in a settings.yaml file. There is a sample file [here](resources/sample_settings.yaml), which can be used as basis. Then, set an environment var `FLOWCEPT_SETTINGS_PATH` with the absolute path to the yaml file. If you do not follow this step, the default values defined [here](resources/sample_settings.yaml) will be used.

4. See the [Jupyter Notebooks](notebooks) and [Examples directory](examples) for utilization examples.

## Installing and Running with Docker

To use containers instead of installing FlowCept's dependencies on your host system, we provide a [Dockerfile](deployment/Dockerfile) alongside a [docker-compose.yml](deployment/compose.yml) for dependent services (e.g., Redis, MongoDB).  

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

### Simple Example with Decorators Instrumentation

In addition to existing adapters to Dask, MLFlow, and others (it's extensible for any system that generates data), FlowCept also offers instrumentation via @decorators. 

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

## Performance Tuning for Performance Evaluation

In the settings.yaml file, the following variables might impact interception performance:

```yaml
main_redis:
  buffer_size: 50
  insertion_buffer_time_secs: 5

plugin:
  enrich_messages: false
```

And other variables depending on the Plugin. For instance, in Dask, timestamp creation by workers add interception overhead. As we evolve the software, other variables that impact overhead appear and we might not stated them in this README file yet. If you are doing extensive performance evaluation experiments using this software, please reach out to us (e.g., create an issue in the repository) for hints on how to reduce the overhead of our software.

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

Current code is compatible with this version: amdsmi==24.6.2+2b02a07
Which was installed using Frontier's /opt/rocm-6.2.0/share/amd_smi

## Torch Dependencies

Some unit tests utilize `torch==2.2.2`, `torchtext=0.17.2`, and `torchvision==0.17.2`. They are only really needed to run some tests and will be installed if you run `pip install flowcept[ml_dev]` or `pip install flowcept[all]`. If you want to use FlowCept with Torch, please adapt torch dependencies according to your project's dependencies.

## Cite us

If you used FlowCept in your research, consider citing our paper.

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

Please note that this a research software. We encourage you to give it a try and use it with your own stack. We are continuously working on improving documentation and adding more examples and notebooks, but we are still far from a good documentation covering the whole system. If you are interested in working with FlowCept in your own scientific project, we can give you a jump start if you reach out to us. Feel free to [create an issue](https://github.com/ORNL/flowcept/issues/new), [create a new discussion thread](https://github.com/ORNL/flowcept/discussions/new/choose) or drop us an email (we trust you'll find a way to reach out to us :wink:).

## Acknowledgement

This research uses resources of the Oak Ridge Leadership Computing Facility at the Oak Ridge National Laboratory, which is supported by the Office of Science of the U.S. Department of Energy under Contract No. DE-AC05-00OR22725.
