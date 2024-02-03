from threading import Thread
from time import sleep
import pika
import json
from typing import Dict

from flowcept.commons.utils import get_utc_now, get_status_from_str
from flowcept.commons.flowcept_dataclasses.task_message import TaskMessage
from flowcept.flowceptor.plugins.base_interceptor import (
    BaseInterceptor,
)


class ZambezeInterceptor(BaseInterceptor):
    def __init__(self, plugin_key="zambeze"):
        super().__init__(plugin_key)
        self._consumer_tag = None
        self._channel = None
        self._observer_thread: Thread = None

    def prepare_task_msg(self, zambeze_msg: Dict) -> TaskMessage:
        task_msg = TaskMessage()
        task_msg.utc_timestamp = get_utc_now()
        task_msg.campaign_id = zambeze_msg.get("campaign_id", None)
        task_msg.task_id = zambeze_msg.get("activity_id", None)
        task_msg.activity_id = zambeze_msg.get("name", None)
        task_msg.dependencies = zambeze_msg.get("depends_on", None)
        task_msg.custom_metadata = {
            "command": zambeze_msg.get("command", None)
        }
        task_msg.status = get_status_from_str(
            zambeze_msg.get("activity_status", None)
        )
        task_msg.used = {
            "args": zambeze_msg.get("arguments", None),
            "kwargs": zambeze_msg.get("kwargs", None),
            "files": zambeze_msg.get("files", None),
        }
        return task_msg

    def start(self) -> "ZambezeInterceptor":
        super().start()
        self._observer_thread = Thread(target=self.observe)
        self._observer_thread.start()
        return self

    def stop(self) -> bool:
        self.logger.debug("Interceptor stopping...")
        super().stop()
        try:
            self._channel.basic_cancel(self._consumer_tag)
        except Exception as e:
            self.logger.warning(
                f"This exception is expected to occur after "
                f"channel.basic_cancel: {e}"
            )
        sleep(2)
        self._observer_thread.join()
        self.logger.debug("Interceptor stopped.")
        return True

    def observe(self):
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=self.settings.host, port=self.settings.port
            )
        )
        self._channel = connection.channel()
        self._channel.queue_declare(queue=self.settings.queue_name)
        self._consumer_tag = self._channel.basic_consume(
            queue=self.settings.queue_name,
            on_message_callback=self.callback,
            auto_ack=True,
        )
        self.logger.debug("Waiting for Zambeze messages.")
        try:
            self._channel.start_consuming()
        except Exception as e:
            self.logger.warning(
                f"If this exception happens after "
                f"channel.start_consuming finishes, it is expected:\n {e}"
            )

    def _intercept(self, body_obj):
        self.logger.debug(
            f"I'm a Zambeze interceptor and I need to intercept this:"
            f"\n\t{json.dumps(body_obj)}"
        )
        task_msg = self.prepare_task_msg(body_obj)
        self.intercept(task_msg)

    def callback(self, ch, method, properties, body):
        body_obj = json.loads(body)
        if self.settings.key_values_to_filter is not None:
            for key_value in self.settings.key_values_to_filter:
                if key_value.key in body_obj:
                    if body_obj[key_value.key] == key_value.value:
                        self._intercept(body_obj)
                        break
        else:
            self._intercept(body_obj)
