from typing import Dict

from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.flowceptor.consumers.base_consumer import BaseConsumer


class MyConsumer(BaseConsumer):

    def __init__(self):
        super().__init__()

    def message_handler(self, msg_obj: Dict) -> bool:
        if msg_obj.get('type', '') == 'task':
            msg = TaskObject.from_dict(msg_obj)
            print(msg)
            if msg.used:
                print(f"\t\tUsed: {msg.used}")
            if msg.generated:
                print(f"\t\tGenerated: {msg.generated}")
            if msg.custom_metadata:
                print(f"\t\tCustom Metadata: {msg.custom_metadata}")

            print()
            print()
        else:
            print(f"We got a msg with different type: {msg_obj.get("type", None)}")
        return True


if __name__ == "__main__":

    print("Starting consumer indefinitely. Press ctrl+c to stop")
    consumer = MyConsumer()
    consumer.start(daemon=False)
