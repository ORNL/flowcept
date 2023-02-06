import pika
import sys
import json
from typing import Dict

from flowcept.commons.utils import get_utc_now, get_status_from_str
from flowcept.commons.flowcept_data_classes import TaskMessage, Status
from flowcept.flowceptor.plugins.base_interceptor import (
    BaseInterceptor,
)


class ZambezeInterceptor(BaseInterceptor):
    def __init__(self, plugin_key="zambeze"):
        super().__init__(plugin_key)

    def prepare_task_msg(self, zambeze_msg: Dict) -> TaskMessage:
        task_msg = TaskMessage()
        task_msg.utc_timestamp = get_utc_now()
        task_msg.experiment_id = zambeze_msg.get("campaign_id")
        task_msg.task_id = zambeze_msg.get("activity_id")
        task_msg.activity_id = zambeze_msg.get("name")
        task_msg.custom_metadata = {"command": zambeze_msg.get("command")}
        task_msg.status = get_status_from_str(
            zambeze_msg.get("activity_status")
        )
        task_msg.used = {
            "args": zambeze_msg["arguments"],
            "kwargs": zambeze_msg["kwargs"],
            "files": zambeze_msg["files"],
        }
        return task_msg

    def observe(self):
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=self.settings.host, port=self.settings.port
            )
        )
        channel = connection.channel()
        channel.queue_declare(queue=self.settings.queue_name)
        channel.basic_consume(
            queue=self.settings.queue_name,
            on_message_callback=self.callback,
            auto_ack=True,
        )

        print(" [*] Waiting for Zambeze messages. To exit press CTRL+C")
        channel.start_consuming()

    def callback(self, ch, method, properties, body):
        body_obj = json.loads(body)

        for key_value in self.settings.key_values_to_filter:
            if key_value.key in body_obj:
                if body_obj[key_value.key] == key_value.value:
                    print(
                        f"I'm an interceptor and I need to intercept this:"
                        f"\n\t{json.dumps(body_obj)}"
                    )
                    task_msg = self.prepare_task_msg(body_obj)
                    self.intercept(task_msg)
                    break


if __name__ == "__main__":
    try:
        # TODO: allow passing the interceptor key in the argv
        interceptor = ZambezeInterceptor("zambeze1")
        interceptor.observe()
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(0)
