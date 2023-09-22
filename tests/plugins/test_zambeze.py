from time import sleep
import unittest
import json
import pika
from uuid import uuid4

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept import ZambezeInterceptor, FlowceptConsumerAPI
from flowcept.flowceptor.plugins.zambeze.zambeze_dataclasses import (
    ZambezeMessage,
)


class TestZambeze(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestZambeze, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger().get_logger()
        interceptor = ZambezeInterceptor()
        self.consumer = FlowceptConsumerAPI(interceptor)

        self._connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                interceptor.settings.host,
                interceptor.settings.port,
            )
        )
        self._channel = self._connection.channel()
        self._queue_name = interceptor.settings.queue_name
        self._channel.queue_declare(queue=self._queue_name)

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
            routing_key=self._queue_name,
            body=json.dumps(msg.__dict__),
        )

        self.logger.debug(" [x] Sent msg")
        sleep(5)
        self._connection.close()
        sleep(10)
        doc_dao = DocumentDBDao()
        assert len(doc_dao.task_query({"task_id": act_id})) > 0
        self.consumer.stop()
        sleep(2)


if __name__ == "__main__":
    unittest.main()
