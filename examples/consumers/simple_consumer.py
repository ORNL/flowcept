from typing import Dict

from flowcept.flowceptor.consumers.base_consumer import BaseConsumer


class MyConsumer(BaseConsumer):

    def __init__(self):
        super().__init__()

    def message_handler(self, msg_obj: Dict) -> bool:
        if msg_obj.get('type', '') == 'task':
            print(msg_obj)
        else:
            print(f"We got a msg with different type: {msg_obj.get("type", None)}")
        return True


if __name__ == "__main__":

    print("Starting consumer indefinitely. Press ctrl+c to stop")
    consumer = MyConsumer()
    consumer.start(daemon=False)
