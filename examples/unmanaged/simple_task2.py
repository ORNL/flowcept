"""
This example shows different ways of creating Flowcept tasks.
"""
import uuid
from time import sleep

from flowcept import Flowcept, FlowceptTask, flowcept_task


@flowcept_task(output_names="beta")
def super_func4(alpha):
    return alpha*1.1


if __name__ == "__main__":
    agent1 = str(uuid.uuid4())
    campaign_id = "my_super_campaign"
    workflow_name = "My First Workflow"

    flowcept = Flowcept(start_persistence=False,
                        save_workflow=True,
                        workflow_name=workflow_name,
                        campaign_id=campaign_id).start()

    # Direct task event emission:
    FlowceptTask(activity_id="super_func1", used={"x": 1}, agent_id=agent1, tags=["tag1"]).send()

    # Register the event start, save it in a local buffer
    with FlowceptTask(activity_id="super_func2", used={"y": 1}, agent_id=agent1, tags=["tag2"]) as t2:
        sleep(0.5)
        t2.end(generated={"o": 3})
        # Register the event end, emit the complete task event

    # Same as t2 but without context management
    t3 = FlowceptTask(activity_id="super_func3", used={"z": 1}, agent_id=agent1, tags=["tag3"])
    sleep(0.1)
    t3.end(generated={"w": 1})

    super_func4(alpha=0.5)

    flowcept.stop()

    flowcept_messages = Flowcept.read_buffer_file()
    assert len(flowcept_messages) == 5
