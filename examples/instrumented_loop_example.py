import random
from time import sleep

from flowcept import Flowcept, FlowceptLoop

# EXAMPLE 1:


iterations = range(1, 5)

with Flowcept():

    loop = FlowceptLoop(iterations)         # See also: FlowceptLightweightLoop
    for item in loop:
        loss = random.random()
        sleep(0.05)
        print(item, loss)
        # The following is optional, in case you want to capture values generated inside the loop.
        loop.end_iter({"item": item, "loss": loss})

docs = Flowcept.db.get_tasks_from_current_workflow()
assert len(docs) == len(iterations)


# EXAMPLE 2: WHILE LOOP EXAMPLE
# The following code is equivalent to:
# while layer_for_control_update <= num_layers - 1:
#     ... loop code ...
#    layer_for_control_update += 1

layer_for_control_update = 2
num_layers = 6


def do_work(layer_ix: int) -> dict:
    """Dummy per-iteration work that returns something to log."""
    # simulate some computation
    value = layer_ix * 10
    return {"value": value}


# Wrap the loop with FlowceptLoop
iterations = range(layer_for_control_update, num_layers)

# You can create with_flowcept flags
with_flowcept = True

if with_flowcept:
    loop = FlowceptLoop(
        items=iterations,
        loop_name="control_loop",
        item_name="layer_ix",
        # parent_task_id="optional-parent-id",
        # workflow_id="optional-workflow-id",
    )
    iterations = loop


for layer_ix in iterations:
    # Your loop body
    result = do_work(layer_ix)
    print(f"Processed layer {layer_ix}, result={result}")

    if with_flowcept:
        # Record per-iteration outputs
        iterations.end_iter({
            "layer_ix": layer_ix,
            "status": "updated",
            **result,                 # attach any metrics you computed
        })

if with_flowcept:
    docs = Flowcept.db.get_tasks_from_current_workflow()
    assert len(docs) == len(iterations)


# EXAMPLE 3: WHILE LOOP EXAMPLE