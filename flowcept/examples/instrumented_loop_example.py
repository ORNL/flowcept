import random
from time import sleep

from flowcept import Flowcept, FlowceptLoop

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
