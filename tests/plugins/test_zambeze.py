from time import sleep
import unittest
import json
import threading
import pika
from uuid import uuid4

from flowcept.flowcept_consumer.main import (
    main,
)
from flowcept.commons.doc_db.document_db_dao import DocumentDBDao
from flowcept.flowceptor.plugins.zambeze.zambeze_interceptor import (
    ZambezeInterceptor,
)
from flowcept.flowceptor.plugins.zambeze.zambeze_dataclasses import (
    ZambezeMessage,
)


class TestZambeze(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestZambeze, self).__init__(*args, **kwargs)
        self.interceptor = ZambezeInterceptor()

        self._connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                self.interceptor.settings.host,
                self.interceptor.settings.port,
            )
        )
        self._channel = self._connection.channel()
        self._channel.queue_declare(
            queue=self.interceptor.settings.queue_name
        )
        threading.Thread(target=self.interceptor.observe, daemon=True).start()
        threading.Thread(target=main, daemon=True).start()

    def test_send_message(self):
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
                "depends_on": [],
            }
        )

        self._channel.basic_publish(
            exchange="",
            routing_key=self.interceptor.settings.queue_name,
            body=json.dumps(msg.__dict__),
        )

        print(" [x] Sent msg")
        self._connection.close()
        sleep(10)
        doc_dao = DocumentDBDao()
        assert len(doc_dao.find({"task_id": act_id})) > 0


if __name__ == "__main__":
    unittest.main()
