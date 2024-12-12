from time import sleep

from flowcept import Flowcept, flowcept_loop

epochs = range(1, 3)
with Flowcept():
    for _ in flowcept_loop(items=epochs, loop_name="epochs", item_name='epoch'):
        sleep(0.05)

docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
print(len(docs))
assert len(docs) == 3  # 1 (parent_task) + 2 (sub_tasks)
