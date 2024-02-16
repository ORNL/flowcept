from time import sleep
import unittest
import json
import pika
from uuid import uuid4

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept import ZambezeInterceptor, FlowceptConsumerAPI
from flowcept.flowceptor.adapters.zambeze.zambeze_dataclasses import (
    ZambezeMessage,
)
from flowcept.commons.utils import assert_by_querying_task_collections_until


class TestZambeze(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestZambeze, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()
        interceptor = ZambezeInterceptor()
        self.consumer = FlowceptConsumerAPI(interceptor)
        self._connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                interceptor.settings.host,
                interceptor.settings.port,
            )
        )
        self._channel = self._connection.channel()
        self._queue_names = interceptor.settings.queue_names

        self._channel.queue_declare(queue=self._queue_names[0])
        self.consumer.start()

    def test_send_message(self):
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
        assert assert_by_querying_task_collections_until(
            DocumentDBDao(),
            {"task_id": act_id},
        )
        self.consumer.stop()


if __name__ == "__main__":
    unittest.main()
