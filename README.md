[![Build](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml)
[![PyPI](https://badge.fury.io/py/flowcept.svg)](https://pypi.org/project/flowcept)
[![Tests](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml)
[![Code Formatting](https://github.com/ORNL/flowcept/actions/workflows/run-checks.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/run-checks.yml)
[![License: MIT](https://img.shields.io/github/license/ORNL/flowcept)](LICENSE)

# FlowCept

FlowCept is a runtime data integration system that empowers any data processing system to capture and query workflow provenance data using data observability, requiring minimal or no changes in the target system code. It seamlessly integrates data from multiple workflows, enabling users to comprehend complex, heterogeneous, and large-scale data from various sources in federated environments.

FlowCept is intended to address scenarios where multiple workflows in a science campaign or in an enterprise run and generate important data to be analyzed in an integrated manner. Since these workflows may use different data manipulation tools (e.g., provenance or lineage capture tools, database systems, performance profiling tools) or can be executed within different parallel computing systems (e.g., Dask, Spark, Workflow Management Systems), its key differentiator is the capability to seamless and automatically integrate data from various workflows using data observability. It builds an integrated data view at runtime enabling end-to-end exploratory data analysis and monitoring. It follows [W3C PROV](https://www.w3.org/TR/prov-overview/) recommendations for its data schema. It does not require changes in user codes or systems (i.e., instrumentation). All users need to do is to create adapters for their systems or tools, if one is not available yet. In addition to observability, we provide instrumentation options for convenience. For example, by adding a `@flowcept_task` decorator on functions, FlowCept will observe their executions when they run. Also, we provide special features for PyTorch modules. Adding `@torch_task` to them will enable extra model inspection to be captured and integrated in the database at runtime.

Currently, FlowCept provides adapters for: [Dask](https://www.dask.org/), [MLFlow](https://mlflow.org/), [TensorBoard](https://www.tensorflow.org/tensorboard), and [Zambeze](https://github.com/ORNL/zambeze). 

See the [Jupyter Notebooks](notebooks) and [Examples](examples) for utilization examples.

See the [Contributing](CONTRIBUTING.md) file for guidelines to contribute with new adapters. Note that we may use the term 'plugin' in the codebase as a synonym to adapter. Future releases should standardize the terminology to use adapter.

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
