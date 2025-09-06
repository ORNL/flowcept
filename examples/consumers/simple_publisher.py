from typing import Dict

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.consumers.base_consumer import BaseConsumer
from flowcept.instrumentation.flowcept_task import flowcept_task


class MyPublisher:

    def __init__(self):
        self.f = Flowcept(start_persistence=False).start()

    @flowcept_task
    def send_message(self, msg: Dict):
        print("Going to send", msg)
        return {"success": True}


if __name__ == "__main__":

    publisher = MyPublisher()
    publisher.send_message({"msg": "Hello!"})
    publisher.f.stop()
