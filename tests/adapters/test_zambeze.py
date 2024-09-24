from time import sleep
import unittest
import json
import pika
from uuid import uuid4

from pika.exceptions import AMQPConnectionError

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept import ZambezeInterceptor, Flowcept, TaskQueryAPI
from flowcept.flowceptor.adapters.zambeze.zambeze_dataclasses import (
    ZambezeMessage,
)
from flowcept.commons.utils import assert_by_querying_tasks_until


class TestZambeze(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestZambeze, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()
        interceptor = ZambezeInterceptor()
        try:
            self._connected = False
            self._connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    interceptor.settings.host,
                    interceptor.settings.port,
                )
            )
            self._connected = self._connection.is_open
        except AMQPConnectionError:
            print("Failed to connect to RabbitMQ. Is it running?")
            return
        except Exception as e:
            print(f"An error occurred: {e}")
            return

        self.consumer = Flowcept(interceptor)
        self._channel = self._connection.channel()
        self._queue_names = interceptor.settings.queue_names
        self._channel.queue_declare(queue=self._queue_names[0])
        self.consumer.start()

    def test_send_message(self):
        if not self._connected:
            self.logger.warning(
                "RabbitMQ was not found. Skipping this " "Zambeze test."
            )
            assert True
            return
        another_act_id = str(uuid4())
        act_id = str(uuid4())
        msg = ZambezeMessage(
            **{
                "name": "ImageMagick",
                "activity_id": act_id,
                "campaign_id": "campaign-uuid",
                "origin_agent_id": "def-uuid",
                "files": ["globus://Users/6o1/file.txt"],
                "command": "convert",
                "activity_status": "CREATED",
                "arguments": [
                    "-delay",
                    "20",
                    "-loop",
                    "0",
                    "~/tests/campaigns/imagesequence/*.jpg",
                    "a.gif",
                ],
                "kwargs": {},
                "depends_on": [another_act_id],
            }
        )

        self._channel.basic_publish(
            exchange="",
            routing_key=self._queue_names[0],
            body=json.dumps(msg.__dict__),
        )
        print("Zambeze Activity_id", act_id)
        self.logger.debug(" [x] Sent msg")
        sleep(5)
        self._connection.close()
        assert assert_by_querying_tasks_until({"task_id": act_id})
        self.consumer.stop()


if __name__ == "__main__":
    unittest.main()
