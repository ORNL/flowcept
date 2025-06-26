"""Zambeze interceptor module."""

import uuid
from threading import Thread
from time import sleep
import paho.mqtt.client as mqtt
import json
from typing import Dict
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.adapters.base_interceptor import (
    BaseInterceptor,
)


class MQTTBrokerInterceptor(BaseInterceptor):
    """Zambeze interceptor."""

    def __init__(self, plugin_key="broker_mqtt"):
        super().__init__(plugin_key)

        assert self.settings.get("protocol") == "mqtt3.1.1", "We only support mqtt3.1.1 for this interceptor."
        self._host = self.settings.get("host", "localhost")
        self._port = self.settings.get("port", 1883)
        self._username = self.settings.get("username", "username")
        self._password = self.settings.get("password", None)
        self._queues = self.settings.get("queues")
        self._qos = self.settings.get("qos", 2)
        self._id = str(id(self))

        self._tracked_keys = self.settings.get("tracked_keys")
        self._task_subtype = self.settings.get("task_subtype", None)
        self._client: mqtt.Client = None

        self._observer_thread: Thread = None

    def _connect(self):
        """Establish a connection to the MQTT broker."""
        try:
            self._client = mqtt.Client(client_id=self._id, clean_session=False, protocol=mqtt.MQTTv311)
            self._client.username_pw_set(self._username, self._password)

            self._client.on_message = self.callback
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect

            self.logger.debug("Connecting to MQTT broker...")
            self._client.connect(self._host, self._port, 60)
            self.logger.debug("Connected.")
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            raise e

    def _on_connect(self, *_):
        """Handle connection events and subscribe to the topic."""
        for q in self._queues:
            self.logger.debug(f"Client {self._id} connected to MQTT queue {q}. Waiting for messages...")
            self._client.subscribe(q, qos=self._qos)

    def callback(self, _, __, msg):
        """Implement the callback."""
        msg_str = msg.payload.decode()
        topic = msg.topic
        self.logger.debug(f"Received message: '{msg_str}' on topic '{topic}'")

        msg_dict = json.loads(msg_str)
        msg_dict["topic"] = topic

        task_msg = self.prepare_task_msg(msg_dict)
        self.intercept(task_msg.to_dict())

    def _on_disconnect(self, *_):
        """Handle disconnections and attempt reconnection."""
        self.logger.warning("MQTT Observer Client Disconnected.")

    def start(self, bundle_exec_id) -> "MQTTBrokerInterceptor":
        """Start it."""
        super().start(bundle_exec_id)
        self._observer_thread = Thread(target=self.observe, daemon=True)
        self._observer_thread.start()
        return self

    def observe(self):
        """Start the MQTT loop."""
        self._connect()
        self._client.loop_forever()

    def prepare_task_msg(self, msg: Dict) -> TaskObject:
        """Prepare a task."""
        task_dict = {}
        custom_metadata = {"topic": msg.get("topic", None)}
        for key in self._tracked_keys:
            if key != "custom_metadata":
                if self._tracked_keys.get(key):
                    task_dict[key] = msg.get(self._tracked_keys.get(key), None)
            else:
                cm = self._tracked_keys.get("custom_metadata", None)
                if cm and len(cm):
                    for k in cm:
                        custom_metadata[k] = msg[k]
                    task_dict["custom_metadata"] = custom_metadata

        if isinstance(task_dict.get("used"), str):
            task_dict["used"] = {"payload": task_dict.get("used")}

        if "task_id" not in task_dict:
            task_dict["task_id"] = str(uuid.uuid4())

        task_obj = TaskObject.from_dict(task_dict)
        task_obj.subtype = self._task_subtype

        if task_obj.campaign_id is None:
            task_obj.campaign_id = Flowcept.campaign_id

        if task_obj.workflow_id is None:
            task_obj.workflow_id = Flowcept.current_workflow_id

        print(task_obj)
        return task_obj

    def stop(self) -> bool:
        """Stop it."""
        self.logger.debug("Interceptor stopping...")
        super().stop()
        try:
            self._client.disconnect()
        except Exception as e:
            self.logger.warning(f"This exception is expected to occur after channel.basic_cancel: {e}")
        sleep(2)
        self._observer_thread.join()
        self.logger.debug("Interceptor stopped.")
        return True
