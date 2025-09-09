Provenance Capture Methods
================================

This page shows the **practical ways to capture provenance in Flowcept**—from zero-config quick runs to decorators, context managers, adapters, and fully custom tasks. Each section includes a minimal code snippet and links to examples.

.. contents::
   :local:
   :depth: 2


Data Observability Adapters
--------------------------

Flowcept can **observe** external tools and emit provenance automatically.

Supported adapters:

- **MLflow** — `example <https://github.com/ORNL/flowcept/blob/main/examples/mlflow_example.py>`_
- **Dask** — `example <https://github.com/ORNL/flowcept/blob/main/examples/dask_example.py>`_
- **TensorBoard** — `example <https://github.com/ORNL/flowcept/blob/main/examples/tensorboard_example.py>`_

Install the extras you need (from README), then configure the adapter in your settings file.  
Adapters capture runs, tasks, metrics, and artifacts and push them through Flowcept’s pipeline (MQ → DB).

Decorators
--------------------------

Use decorators to mark functions as **workflows** or **tasks** with almost no code changes.

``@flowcept`` (wrap a “main” function as a workflow)
~~~~~~~~~~~~~~~

.. code-block:: python

   from flowcept.instrumentation.flowcept_decorator import flowcept

   @flowcept
   def main():
       # Your workflow code here
       

   if __name__ == "__main__":
       main()

**When to use**: a single entrypoint (e.g., ``main``) that represents the whole workflow.  
**Effect**: creates a workflow context and captures enclosed calls (including decorated tasks).

``@flowcept_task`` (mark a function as a task)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``@flowcept_task`` decorator wraps a Python function as a **provenance task**.  
When the function executes, Flowcept captures its inputs (``used``), outputs (``generated``), execution metadata, telemetry (if enabled), and publishes them as provenance messages.

Simple Example (works for most)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from flowcept import Flowcept, flowcept_task

   @flowcept_task(output_names="y")  # output_names is optional.
   def mult_two(x: int) -> int:
       return 2 * x

   with Flowcept(workflow_name="demo"):
       y = mult_two(21)

   # Captured provenance will show {"used": {"x": 21}, "generated": {"y": 42}}
   # Without the output_names, the generated dict will show {"arg_0": 42}

**Options & Behavior** 

**Inputs (``used``)**  
- Function arguments are automatically bound to their parameter names using Python’s introspection.  
- Example: ``double(21)`` → stored as ``{"x": 21}`` instead of ``{"arg_0": 21}``.  
- If an ``argparse.Namespace`` is passed, its attributes are flattened into key-value pairs.  
- Internally this is done by the **default args handler**. You may override it by passing ``args_handler=...`` in the decorator.

**Outputs (``generated``)**  
- By default, the return value is stored under generic keys.  
- Using ``output_names`` improves semantics:  
  - ``@flowcept_task(output_names="y")`` maps a scalar result to ``{"y": result}``.  
  - If the function returns a tuple/list and ``output_names`` has the same length, elements are mapped accordingly.  
- If the function returns a **dict**, it is passed through directly as ``generated`` (with minimal normalization).

**Optional Metadata**
- ``workflow_id``: by default, inherits the current workflow’s ID. Can be overridden if passed as a keyword argument.  
- ``campaign_id``: groups tasks under a campaign. Defaults to the current Flowcept campaign.  
- ``tags``: free-form labels (list or string) attached to the task, useful for filtering.  
- ``custom_metadata``: arbitrary dictionary to attach extra metadata.  

**Telemetry**
- If telemetry capture is enabled, system metrics (CPU, GPU, memory, etc.) are recorded at the start and end of the task.

**Error Handling**
- If the wrapped function raises an exception, provenance is still captured with ``status=ERROR`` and the exception message recorded in the ``stderr`` field..

Advanced Usage
^^^^^^^^^^^^^^

.. code-block:: python

   from flowcept import flowcept_task

   @flowcept_task(
       output_names=["y", "z"],       # map tuple outputs
       tags=["math", "demo"],         # attach tags
       custom_metadata={"owner": "devX"}  # arbitrary extra info
   )
   def compute(x):
       return x * 2, x * 3

   result = compute(5)
   # generated = {"y": 10, "z": 15}
   # tags = ["math", "demo"]
   # custom_metadata = {"owner": "devX"}

---

Custom Arguments Handler and Understanding Arguments Serialization
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The arguments handler in ``@flowcept_task`` defines how **function inputs and outputs** are turned into provenance-friendly dictionaries.  
By default, Flowcept uses ``default_args_handler`` to capture arguments, flatten ``argparse.Namespace`` inputs, and handle non-serializable objects.

**Serialization of Inputs**


If a function argument or output is not JSON-serializable, Flowcept will try to convert it automatically (if ``settings.project.replace_non_json_serializable`` is enabled in your ``settings.yaml``):

- Objects with ``to_flowcept_dict()`` or ``to_dict()`` → converted using those methods  
- Objects that have `__dict__` method and is kept in its internal list of (``__DICT__CLASSES``) → converted using ``__dict__``  
- All other objects → replaced by a string ``<ClassName>_instance_id_<id>``  

This prevents crashes while still preserving some information about the object identity.

Providing a Custom Handler
"""""""""""""""""""""""""""

Developers can override this behavior with their own ``args_handler`` function.  
For example, suppose you want to **drop** the input argument ``very_big_list`` and the output ``super_large_matrix``:

.. code-block:: python

   ARGS_TO_DROP = ["very_big_list", "super_large_matrix"]
   
   def custom_args_handler(*args, **kwargs):
       if len(args):
           raise Exception("In this simple example, we are assuming that"
                           "functions will be called using named args only.")
       handled = {}
       # Add all args/kwargs normally
       for i, arg in enumerate(args):
           handled[f"arg_{i}"] = arg
       handled.update(kwargs)

       # Drop unwanted inputs
       for k in ARGS_TO_DROP:
           handled.pop(k, None)
       
       return handled

   from flowcept import flowcept_task

   @flowcept_task(args_handler=custom_args_handler, output_names="result")
   def heavy_function(x, very_big_list, super_large_matrix):
       # some expensive computation
       return x * 2
   
   # Only "x" and "result" will be recorded in the provenance.
   # If using this specific custom_args_handler example, make sure you call the 
   # function using named arguments so the expected behavior happens:
   # result = heavy_function(x=x, 
   #                         very_big_list=very_big_list,
   #                         super_large_matrix=super_large_matrix)


Summary
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- ``used``: bound inputs, derived from function args (names are preserved if possible).  
- ``generated``: outputs, improved with ``output_names`` or direct dict returns.  
- ``workflow_id`` / ``campaign_id``: control task grouping in provenance.  
- ``tags`` and ``custom_metadata``: user-controlled metadata.  
- ``args_handler``: optional override to customize how inputs/outputs are serialized.  
- By default, Flowcept captures **all arguments** and sanitizes non-serializable objects.  
- With a **custom args handler**, you control exactly what goes into provenance (e.g., drop, rename, or transform arguments).  
- This is especially useful when handling **large inputs** (big matrices, tensors) that you don’t want persisted in provenance.

This flexibility allows Flowcept to adapt to lightweight HPC tasks, ML training steps, or fine-grained function-level tracing with minimal code changes.


``@telemetry_flowcept_task`` (task with telemetry)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Same usage as ``@flowcept_task``, but optimized to **capture telemetry** (CPU/GPU/memory) for the task:

.. code-block:: python

   from flowcept import telemetry_flowcept_task

   @telemetry_flowcept_task
   def train_step(batch):
       # ... your training logic ...
       return 0.123

**When to use**: you want per-task telemetry without writing custom telemetry plumbing.

``@lightweight_flowcept_task`` (ultra-low-overhead task)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Optimized for **HPC** and tight loops; minimal interception overhead:

.. code-block:: python

   from flowcept import lightweight_flowcept_task

   @lightweight_flowcept_task
   def fast_op(x):
       return x + 1

**When to use**: massive iteration counts, sensitive microbenchmarks, or very low overhead needs.



Loop Instrumentation
~~~~~~~~~~~~~~~~~~~~

Instrument iterative loops directly (see
`loop example <https://github.com/ORNL/flowcept/blob/main/examples/instrumented_loop_example.py>`_).  
Combine the context manager (below) with per-iteration tasks or custom events.

.. code-block:: python

   with Flowcept():

    loop = FlowceptLoop(range(5))         # See also: FlowceptLightweightLoop
    for item in loop:
        loss = random.random()
        sleep(0.05)
        print(item, loss)
        # The following is optional, in case you want to capture values generated inside the loop.
        loop.end_iter({"item": item, "loss": loss})


FlowceptLoop vs FlowceptLightweightLoop
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

TODO

PyTorch Models
~~~~~~~~~~~~~~

Flowcept can capture provenance directly from PyTorch models.  
Use the ``@flowcept_torch`` decorator to wrap an ``nn.Module`` so that each ``forward`` call is automatically tracked.


.. code-block:: python

   import torch
   import torch.nn as nn
   import torch.optim as optim
   from flowcept import flowcept_torch

   # Instrument the model with @flowcept_torch
   @flowcept_torch
   class MyNet(nn.Module):
       def __init__(self):
           super().__init__()
           self.fc = nn.Linear(10, 1)

       def forward(self, x):
           return self.fc(x)

   # Dummy training data
   x = torch.randn(100, 10)   # 100 samples, 10 features
   y = torch.randn(100, 1)    # 100 targets

   model = MyNet()
   optimizer = optim.SGD(model.parameters(), lr=0.01)
   loss_fn = nn.MSELoss()

   # Simple training loop
   for epoch in range(3):
       optimizer.zero_grad()
       out = model(x)               # provenance captured here
       loss = loss_fn(out, y)
       loss.backward()
       optimizer.step()
       print(f"Epoch {epoch} - Loss {loss.item()}")

Explanation:

- **@flowcept_torch** instruments the model’s ``forward`` method.  
- Each call to ``model(x)`` is tracked as a provenance task.  
- If enabled (controlled in the settings.yaml file), metadata such as tensor usage, loss values, telemetry are captured.  
- Developers can pass extra constructor arguments like ``get_profile=True`` or ``custom_metadata={...}`` to record richer details.  

This makes it possible to monitor model execution end-to-end with addition of simple @decorators.


MCP Agent Workflows
~~~~~~~~~~~~~~~~~~~

Capture **agentic task provenance** (prompt, tool call, result, timing).
See `MCP Agent example <https://github.com/ORNL/flowcept/blob/main/examples/agents/aec_agent_mock.py>`_.

.. code-block:: python

    from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task

    agent_controller = AgentController() # Must be a subclass of flowcept.flowceptor.consumers.agent.base_agent_context_manager.BaseAgentContextManager
    mcp = FastMCP("AnC_Agent_mock", require_session=True, lifespan=agent_controller.lifespan)
    @mcp.tool()
    @agent_flowcept_task  # Must be in this order. @mcp.tool then @flowcept_task
    def tool_example(x, y, campaign_id=None):
        llm = build_llm_model()
        ctx = mcp.get_context()
        history = ctx.request_context.lifespan_context.history
        messages = generate_prompt(x, y)
        response = llm.invoke(messages)
        result = generate_response(result)
        return result


Context Managers (flexible block capture)
-----------------------------------------

The Flowcept() object
~~~~~~~~~~~~~~~~~~~~~


If your workflow is **scattered across files** or you prefer block scoping, use the context manager:

.. code-block:: python

   from flowcept import Flowcept, flowcept_task

   @flowcept_task(output_names="z")
   def add_one(x): return x + 1

   with Flowcept(workflow_name="my_workflow"):
       # any code in here belongs to the workflow
       z = add_one(7)
       print(z)

**When to use**: flexible block capture, multi-file codebases, or when you can’t (or don’t want to) decorate a top-level function.


Custom Task Creation (fully customizable)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Build tasks programmatically with ``FlowceptTask``—useful for non-decorator flows or custom payloads.
Requires an active workflow (``with Flowcept(...)`` or ``Flowcept().start()``).

.. code-block:: python

   from flowcept import Flowcept
   from flowcept.instrumentation.task import FlowceptTask

   with Flowcept(workflow_name="custom_tasks"):
       # Context-managed publish
       with FlowceptTask(activity_id="download", used={"url": "https://..."}) as t:
           data = b"..."
           t.add_generated({"bytes": len(data)})

       # Or publish explicitly
       task = FlowceptTask(activity_id="parse", used={"bytes": len(data)})
       task.add_generated({"records": 42})
       task.send()  # publishes to MQ

**Notes**:

- Use **context** (``with FlowceptTask(...)``) *or* call ``send()`` explicitly.
- Flows publish to the MQ; persistence/queries require a DB (e.g., MongoDB).


End-to-End Example (Decorators)
-------------------------------

.. code-block:: python

   from flowcept import Flowcept, flowcept_task

   @flowcept_task
   def sum_one(n): return n + 1

   @flowcept_task
   def mult_two(n): return n * 2

   with Flowcept(workflow_name="test_workflow"):
       n = 3
       o1 = sum_one(n)
       o2 = mult_two(o1)
       print(o2)

   # If MongoDB is enabled in settings, you can query:
   # from flowcept import Flowcept
   # print(Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id}))


Querying (MongoDB)
------------------

Once persisted (e.g., to MongoDB), you can query captured provenance:

.. code-block:: python

   from flowcept import Flowcept
   results = Flowcept.db.query({"workflow_id": "<some_workflow_id>"})
   print(results)

.. note::
   Complex historical queries require a persistent database (MongoDB).  
   Without a DB, provenance lives in the MQ (ephemeral/streaming).


References & Examples
---------------------

- Examples directory: https://github.com/ORNL/flowcept/tree/main/examples
- MLflow adapter: https://github.com/ORNL/flowcept/blob/main/examples/mlflow_example.py
- Dask adapter: https://github.com/ORNL/flowcept/blob/main/examples/dask_example.py
- TensorBoard adapter: https://github.com/ORNL/flowcept/blob/main/examples/tensorboard_example.py
- Loop instrumentation: https://github.com/ORNL/flowcept/blob/main/examples/instrumented_loop_example.py
- LLM/PyTorch model: https://github.com/ORNL/flowcept/blob/main/examples/llm_complex/llm_model.py
- MCP Agent tasks: https://github.com/ORNL/flowcept/blob/main/examples/agents/aec_agent_mock.py
- Settings sample: https://github.com/ORNL/flowcept/blob/main/resources/sample_settings.yaml
- Deployment (services): https://github.com/ORNL/flowcept/tree/main/deployment
