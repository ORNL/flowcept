import random
from time import sleep

from flowcept import Flowcept, FlowceptLoop

iterations = 3

with Flowcept():
    loop = FlowceptLoop(iterations)
    for item in loop:
        loss = random.random()
        sleep(0.05)
        print(item, loss)
        # The following is optional, in case you want to capture values generated inside the loop.
        loop.end_iter({"item": item, "loss": loss})

docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
assert len(docs) == iterations + 1  # The whole loop itself is a task
