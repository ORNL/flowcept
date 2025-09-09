Setup and Installation
=======================

.. toctree::
   :maxdepth: 2
   :caption: Contents:


Flowcept can be installed in multiple ways, depending on your needs.

Default Installation
---------------------

To install Flowcept with its basic dependencies from `PyPI <https://pypi.org/project/flowcept/>`_, run:

.. code-block:: bash

   pip install flowcept

This installs the minimal Flowcept package, **not** including MongoDB, Redis, MCP, or any adapter-specific dependencies.

Installing Specific Adapters and Additional Dependencies
---------------------------------------------------------

Flowcept integrates with several tools and services, but you should **only install what you actually need**.  
Good practice is to cherry-pick the extras relevant to your workflow instead of installing them all.

.. code-block:: bash

   pip install flowcept[mongo]         # MongoDB support
   pip install flowcept[mlflow]        # MLflow adapter
   pip install flowcept[dask]          # Dask adapter
   pip install flowcept[tensorboard]   # TensorBoard adapter
   pip install flowcept[kafka]         # Kafka message queue
   pip install flowcept[nvidia]        # NVIDIA GPU runtime capture
   pip install flowcept[telemetry]     # CPU/GPU/memory telemetry capture
   pip install flowcept[lmdb]          # LMDB lightweight database
   pip install flowcept[mqtt]          # MQTT support
   pip install flowcept[llm_agent]     # MCP agent, LangChain, Streamlit integration
   pip install flowcept[llm_google]    # Google GenAI + Flowcept agent support
   pip install flowcept[analytics]     # Extra analytics (seaborn, plotly, scipy)
   pip install flowcept[dev]           # Developer dependencies (docs, tests, lint, etc.)

Installing with Common Runtime Bundle
--------------------------------------

.. code-block:: bash

   pip install flowcept[extras]

The ``extras`` group is a convenience shortcut that bundles the most common runtime dependencies.  
It is intended for users who want a fairly complete, but not maximal, Flowcept environment.

You might choose ``flowcept[extras]`` if:

- You want Flowcept to run out-of-the-box with Redis, telemetry, and MongoDB  
- You prefer not to install each extra one by one  

.. warning::

   If you only need one of these features, install it individually instead of ``extras``.

Install All Optional Dependencies at Once
------------------------------------------

Flowcept provides a combined ``all`` extra, but installing everything into a single environment is **not recommended for users**.  
Many of these dependencies are unrelated and should not be mixed in the same runtime.  
This option is only intended for Flowcept developers who need to test across all adapters and integrations.

.. code-block:: bash

   pip install flowcept[all]

Installing from Source
-----------------------

To install Flowcept from the source repository:

.. code-block:: bash

   git clone https://github.com/ORNL/flowcept.git
   cd flowcept
   pip install .

You can then install specific dependencies similarly as above:

.. code-block:: bash

   pip install .[optional_dependency_name]

This follows the same pattern as above, allowing for a customized installation from source.

Setup
~~~~~

The :doc:`quick_start` example works with just ``pip install flowcept``, no extra setup is required.

For online queries or distributed capture, Flowcept relies on two optional components:

- **Message Queue (MQ)** — message broker / pub-sub / data stream  
- **Database (DB)** — persistent storage for historical queries  

Message Queue (MQ)
-------------------

- Required for anything beyond Quickstart  
- Flowcept publishes provenance data to the MQ during workflow runs  
- Developers can subscribe with custom consumers (see `simple consumer example <https://github.com/ORNL/flowcept/blob/main/examples/consumers/simple_consumer.py>`_)  
- You can monitor or print messages in motion using:

.. code-block:: bash

   flowcept --stream-messages --print

Supported MQs:

- `Redis <https://redis.io>`_ → **default**, lightweight, works on Linux, macOS, Windows, and HPC (tested on Frontier and Summit)  
- `Kafka <https://kafka.apache.org>`_ → for distributed environments or if Kafka is already in your stack  
- `Mofka <https://mofka.readthedocs.io>`_ → optimized for HPC runs  

Database (DB)
--------------

- **Optional**, but required for:
  - Persisting provenance beyond MQ memory/disk buffers  
  - Running complex analytical queries on historical data  

Supported DBs:

- `MongoDB <https://www.mongodb.com>`_ → default, efficient bulk writes + rich query support  
- `LMDB <https://lmdb.readthedocs.io>`_ → lightweight, no external service, basic query capabilities  

Notes
-----

- Without a DB:
  - Provenance remains in the MQ only (persistence not guaranteed)  
  - Complex historical queries are unavailable  
- Flowcept’s architecture is modular: other MQs and DBs (graph, relational, etc.) can be added in the future  
- Deployment examples for MQ and DB are provided in the `deployment <https://github.com/ORNL/flowcept/tree/main/deployment>`_ directory  

Downloading and Starting External Services (MQ or DB)
------------------------------------------------------

Flowcept uses external services for message queues (MQ) and databases (DB). You can start them with Docker Compose, plain containers, or directly on your host.

Using Docker Compose (recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We provide a `Makefile <https://github.com/ORNL/flowcept/blob/main/deployment/Makefile>`_ with shortcuts:

1. **Redis only (no DB)**: ``make services``   (LMDB can be used in this setup as a lightweight DB)  
2. **Redis + MongoDB**: ``make services-mongo``  
3. **Kafka + MongoDB**: ``make services-kafka``  
4. **Mofka only (no DB)**: ``make services-mofka``  

To customize, edit the YAML files in `deployment <https://github.com/ORNL/flowcept/tree/main/deployment>`_ and run:

.. code-block:: bash

   docker compose -f deployment/<compose-file>.yml up -d

Using Docker (without Compose)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See the deployment compose files for expected images and configurations.  
You can adapt them to your environment and use standard ``docker pull / run / exec`` commands.

Running on the Host (no containers)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Install binaries for the service you need:  

   - **macOS**: via `Homebrew <https://brew.sh>`_  

     .. code-block:: bash

        brew install redis
        brew services start redis

   - **Linux**: via your distro package manager (``apt``, ``dnf``, ``yum``, etc.)  
   - **HPC (non-root)**: download prebuilt binaries for your architecture and run them from a directory with ``r+w`` permissions  
   - **Windows**: use `WSL <https://learn.microsoft.com/en-us/windows/wsl/install>`_ to run a Linux distro  

2. Start services normally (``redis-server``, ``mongod``, ``kafka-server-start.sh``, etc.).

Flowcept Settings File
=======================

Flowcept uses a settings file for configuration.

- To create a minimal settings file (**recommended**):

.. code-block:: bash

   flowcept --init-settings

Creates ``~/.flowcept/settings.yaml``.

- To create a full settings file with all options:

.. code-block:: bash

   flowcept --init-settings --full

Also creates ``~/.flowcept/settings.yaml``.

What You Can Configure
-----------------------

- Message queue and database routes, ports, and paths  
- MCP agent ports and LLM API keys  
- Buffer sizes and flush settings  
- Telemetry capture settings  
- Instrumentation and PyTorch details  
- Log levels  
- Data observability adapters  
- And more (see `example file <https://github.com/ORNL/flowcept/blob/main/resources/sample_settings.yaml>`_)  

Custom Settings File
---------------------

Flowcept looks for its settings in the following order:

1. ``~/.flowcept/settings.yaml`` — created by ``flowcept --init-settings``  
2. Environment variable ``FLOWCEPT_SETTINGS_PATH`` — if set, Flowcept will use this  
3. Default sample file — `sample_settings.yaml <https://github.com/ORNL/flowcept/blob/main/resources/sample_settings.yaml>`_  

