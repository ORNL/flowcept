from dataclasses import dataclass
import json
import pytest
import pika

from flowcept.commons.utils import get_mq_settings

from flowcept.flowceptor.plugins.zambeze.zambeze_message import ZambezeMessage

MQ_SETTINGS = get_mq_settings('zambeze')


def get_channel_and_connection():

    connection = pika.BlockingConnection(pika.ConnectionParameters(MQ_SETTINGS.host,
                                                                   MQ_SETTINGS.port))
    channel = connection.channel()
    channel.queue_declare(queue=MQ_SETTINGS.queue_name)

    return channel, connection


@pytest.mark.unit
def test_emit_interceptable_message():
    channel, connection = get_channel_and_connection()

    msg = ZambezeMessage(**{
        "name": "ImageMagick",
        "activity_id": "xyz-uuid",
        "campaign_id": "abc-uuid",
        "origin_agent_id": "def-uuid",
        "files": ["globus://Users/6o1/file.txt"],
        "command": "convert",
        "activity_status": "CREATED",
        "arguments": ["-delay",
                      "20",
                      "-loop",
                      "0",
                      "~/tests/campaigns/imagesequence/*.jpg",
                      "a.gif"],
        "kwargs": {},
        "depends_on": []
    })

    channel.basic_publish(exchange='', routing_key=MQ_SETTINGS.queue_name, body=json.dumps(msg.__dict__))
    print(" [x] Sent msg")
    connection.close()
