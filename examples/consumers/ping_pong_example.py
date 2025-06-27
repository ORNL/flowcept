import threading
import time
from typing import Dict

from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.consumers.base_consumer import BaseConsumer
from flowcept.commons.vocabulary import Status
from flowcept.instrumentation.task_capture import FlowceptTask


class MyConsumer(BaseConsumer):
    def __init__(self):
        super().__init__()

    def message_handler(self, msg_obj: Dict) -> bool:
        if msg_obj.get('type', '') == 'task':
            task = TaskObject.from_dict(msg_obj)
            print(f"\n[CONSUMER] Received task: {task}")

            ping_val = task.used.get("ping")
            if ping_val:
                print(f"[CONSUMER] Pong: received ping -> {ping_val}")
                FlowceptTask(
                    used={"pong": f"pong in response to '{ping_val}'"},
                    activity_id="pong_response",
                ).send()

            pong_val = task.used.get("pong")
            if pong_val:
                print(f"[CONSUMER] Received pong -> {pong_val}")

        else:
            print(f"[CONSUMER] Unknown message type: {msg_obj.get('type', None)}")
        return True


def ping_loop(interval=5):
    i = 0
    while True:
        i += 1
        print(f"[PRODUCER] Sending ping #{i}")
        FlowceptTask(
            used={"ping": f"ping #{i} at {time.time()}"},
            activity_id="ping_task",
        ).send()
        time.sleep(interval)


def main():
    # Start consumer in one thread
    consumer = MyConsumer()
    consumer_thread = threading.Thread(target=consumer.start, kwargs={"daemon": True})
    consumer_thread.start()

    # Start producer in main thread
    Flowcept(start_persistence=False).start()
    ping_loop(interval=5)


if __name__ == "__main__":
    print("Starting Ping-Pong in a single process with threads.")
    print(" - Producer sends ping every 5 seconds")
    print(" - Consumer prints ping and replies with pong\n")
    main()
