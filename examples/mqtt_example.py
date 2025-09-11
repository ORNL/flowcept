# broker_minimal_example.py
import json
import time
import uuid
import paho.mqtt.client as mqtt

from flowcept import Flowcept
from flowcept.configs import settings


def configure_flowcept_for_mqtt():
    """
    Mirror your settings.yaml exactly under adapters.broker_mqtt so the
    MQTTBrokerInterceptor picks it up via self.settings.
    """
    settings.setdefault("adapters", {})
    settings["adapters"]["broker_mqtt"] = {
        "kind": "broker",
        "host": "localhost",
        "port": 30011,
        "protocol": "mqtt3.1.1",
        "queues": ["#"],
        "username": "postman",
        "password": "p",
        "qos": 2,
        "task_subtype": "intersect_msg",
        "tracked_keys": {
            "used": "payload",
            "generated": None,          # ~ in YAML
            "custom_metadata": ["headers", "msgId"],
            "activity_id": "operationId",
            "submitted_at": None,
            "started_at": None,
            "ended_at": None,
            "registered_at": None,
        },
    }


def publish_one_message(
    host="localhost",
    port=30011,
    username="postman",
    password="p",
    topic="flowcept/demo/test",
):
    """
    Publish a single JSON payload with the fields your tracked_keys expect:
    - payload            -> mapped to Task.used
    - headers, msgId     -> copied into Task.custom_metadata
    - operationId        -> mapped to Task.activity_id
    """
    client = mqtt.Client(protocol=mqtt.MQTTv311)
    client.username_pw_set(username, password)
    client.connect(host, port, keepalive=60)

    payload = {
        "payload": {"greeting": "hello from mqtt"},   # becomes Task.used
        "headers": {"x-source": "unit-test", "x-env": "local"},
        "msgId": str(uuid.uuid4()),
        "operationId": "op-xyz-123",                  # becomes Task.activity_id
        # optional extras also okay
        "status": "FINISHED",
    }

    client.publish(topic, json.dumps(payload), qos=2, retain=False)
    client.disconnect()
    return payload


def main():
    # 1) Apply settings that match your YAML
    configure_flowcept_for_mqtt()

    # 2) Start Flowcept in context for the broker_mqtt adapter
    with Flowcept("broker_mqtt"):
        # 3) Start the interceptor (runs MQTT loop in a background thread)
        # Give it a moment to connect/subscribe to "#"
        time.sleep(1.0)

        # 4) Publish one message
        sent = publish_one_message()
        print("Published:", sent)

        # 5) Allow time for ingest
        time.sleep(2.0)

    # 6) (Optional) Query Flowcept DB for the ingested task
    try:
        # Query by nested field in used (payload.greeting)
        tasks = Flowcept.db.query(filter={"used.greeting": "hello from mqtt"})
        if tasks:
            print("Ingested task example:\n", json.dumps(tasks[0], indent=2))
        else:
            print("No tasks found for filter used.greeting == 'hello from mqtt'")
    except Exception as e:
        print(f"DB query failed/skipped: {e}")


if __name__ == "__main__":
    main()
