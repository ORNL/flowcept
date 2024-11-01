Getting Started
===============

Installation and usage instructions are detailed in the following sections.

Installation
------------

Installing flowcept can be accomplished by cloning the GitHub repository and installing with pip using the following terminal commands:

.. code-block:: text

   git clone https://github.com/ORNL/flowcept.git
   cd flowcept
   pip install .

Or it can be installed directly from `PyPI <https://pypi.org/project/flowcept/>`_ with:

.. code-block:: text

   pip install flowcept

Use ``pip install flowcept[all]`` to install all dependencies for all the adapters. Alternatively, dependencies for a particular adapter can be installed; for example, ``pip install flowcept[dask]`` will install only the dependencies for the Dask adapter. The optional dependencies currently available are:

.. code-block:: text

   pip install flowcept[mlflow]        # To install mlflow's adapter
   pip install flowcept[dask]          # To install dask's adapter
   pip install flowcept[tensorboard]   # To install tensorboaard's adapter
   pip install flowcept[kafka]         # To utilize Kafka as the MQ, instead of Redis
   pip install flowcept[nvidia]        # To capture NVIDIA GPU runtime information
   pip install flowcept[analytics]     # For extra analytics features
   pip install flowcept[dev]           # To install dev dependencies

You do not need to install any optional dependencies to run FlowCept without an adapter; for example, if you want to use simple instrumentation. In this case, you need to remove the adapter part from the settings.yaml file.

Usage
-----

To use FlowCept, one needs to start a database and a MQ system. FlowCept currently supports MongoDB as its database and it supports both Redis and Kafka as the MQ system. For convenience, the default needed services can be started using the Docker compose deployment file from the GitHub repository:

.. code-block:: text

   git clone https://github.com/ORNL/flowcept.git
   cd flowcept
   docker compose -f deployment/compose.yml up -d

A simple example of using FlowCept without any adapters is given here:

.. code-block:: python

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
