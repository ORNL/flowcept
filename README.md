[![Build](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/create-release-n-publish.yml)
[![PyPI](https://badge.fury.io/py/flowcept.svg)](https://pypi.org/project/flowcept)
[![Tests](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml)
[![Code Formatting](https://github.com/ORNL/flowcept/actions/workflows/code-formatting.yml/badge.svg)](https://github.com/ORNL/flowcept/actions/workflows/code-formatting.yml)
[![License: MIT](https://img.shields.io/github/license/ORNL/flowcept)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# FlowCept

FlowCept is a runtime data integration system that empowers any data processing system to capture and query workflow 
provenance data using data observability, requiring minimal or no changes in the target system code. It seamlessly integrates data from multiple workflows, enabling users to comprehend complex, heterogeneous, and large-scale data from various sources in federated environments.

FlowCept is intended to address scenarios where multiple workflows in a science campaign or in an enterprise run and generate 
important data to be analyzed in an integrated manner. Since these workflows may use different data manipulation tools (e.g., provenance or lineage capture tools, database systems, performance profiling tools) or can be executed within
different parallel computing systems (e.g., Dask, Spark, Workflow Management Systems), its key differentiator is the 
capability to seamless and automatically integrate data from various workflows using data observability.
It builds an integrated data view at runtime enabling end-to-end exploratory data analysis and monitoring.
It follows [W3C PROV](https://www.w3.org/TR/prov-overview/) recommendations for its data schema.
It does not require changes in user codes or systems (i.e., instrumentation). 
All users need to do is to create adapters for their systems or tools, if one is not available yet. 

Currently, FlowCept provides adapters for: [Dask](https://www.dask.org/), [MLFlow](https://mlflow.org/), [TensorBoard](https://www.tensorflow.org/tensorboard), and [Zambeze](https://github.com/ORNL/zambeze). 

See the [Jupyter Notebooks](notebooks) for utilization examples.

See the [Contributing](CONTRIBUTING.md) file for guidelines to contribute with new adapters. Note that we may use the
term 'plugin' in the codebase as a synonym to adapter. Future releases should standardize the terminology to use adapter.


## Install and Setup:

1. Install FlowCept: 

`pip install .[full]` in this directory (or `pip install flowcept[full]`).

For convenience, this will install all dependencies for all adapters. But it can install
dependencies for adapters you will not use. For this reason, you may want to install 
like this: `pip install .[adapter_key1,adapter_key2]` for the adapters we have implemented, e.g., `pip install .[dask]`.
See [extra_requirements](extra_requirements) if you want to install the dependencies individually.
 
2. Start MongoDB and Redis:

To enable the full advantages of FlowCept, the user needs to run Redis, as FlowCept's message queue system, and MongoDB, as FlowCept's main database system.
The easiest way to start Redis and MongoDB is by using the [docker-compose file](deployment/compose.yml) for its dependent services: 
MongoDB and Redis. You only need RabbitMQ if you want to observe Zambeze messages as well.

3. Define the settings (e.g., routes and ports) accordingly in the [settings.yaml](resources/settings.yaml) file.

4. Start the observation using the Controller API, as shown in the [Jupyter Notebooks](notebooks).

5. To use FlowCept's Query API, see utilization examples in the notebooks.


## Performance Tuning for Performance Evaluation

In the settings.yaml file, the following variables might impact interception performance:

```yaml
main_redis:
  buffer_size: 50
  insertion_buffer_time_secs: 5

plugin:
  enrich_messages: false
```

And other variables depending on the Plugin. For instance, in Dask, timestamp creation by workers add interception overhead.

## See also

- [Zambeze Repository](https://github.com/ORNL/zambeze)

## Cite us

If you used FlowCept for your research, consider citing our paper.

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

Please note that this a research software. We encourage you to give it a try and use it with your own stack. We
are continuously working on improving documentation and adding more examples and notebooks, but we are still far from
a good documentation covering the whole system. If you are interested in working with FlowCept in your own scientific
project, we can give you a jump start if you reach out to us. Feel free to [create an issue](https://github.com/ORNL/flowcept/issues/new), 
[create a new discussion thread](https://github.com/ORNL/flowcept/discussions/new/choose) or drop us an email (we trust you'll find a way to reach out to us :wink: ).

## Acknowledgement

This research uses resources of the Oak Ridge Leadership Computing Facility 
at the Oak Ridge National Laboratory, which is supported by the Office of 
Science of the U.S. Department of Energy under Contract No. DE-AC05-00OR22725.
