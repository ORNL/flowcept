import pika
import sys
import json
from datetime import datetime
import redis

from flowcept.commons.utils import get_mq_settings
from flowcept.commons.configs import REDIS_HOST, REDIS_PORT, REDIS_CHANNEL


def main():

    MQ_SETTINGS = get_mq_settings('zambeze')
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=MQ_SETTINGS.host,
                                                                   port=MQ_SETTINGS.port))
    channel = connection.channel()
    channel.queue_declare(queue=MQ_SETTINGS.queue_name)
    redis_server = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

    def do_interception(message: dict):
        intercepted_msg = dict()
        now = datetime.now()
        dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
        intercepted_msg['time'] = dt_string
        intercepted_msg['application_msg'] = {}
        for key in MQ_SETTINGS.keys_to_intercept:
            if key in message:
                intercepted_msg['application_msg'][key] = message[key]

        print("Sending to Redis!")
        redis_server.publish(REDIS_CHANNEL, json.dumps(intercepted_msg))

    def callback(ch, method, properties, body):
        body_obj = json.loads(body)
        now = datetime.now()
        dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
        print(f"Received msg at {dt_string}: {json.dumps(body_obj)}")

        for key_value in MQ_SETTINGS.key_values_to_filter:
            if key_value.key in body_obj:
                if body_obj[key_value.key] == key_value.value:
                    print("We need to intercept this!")
                    do_interception(message=body_obj)
                    break

    channel.basic_consume(queue=MQ_SETTINGS.queue_name, on_message_callback=callback,
                          auto_ack=True)

    print(' [*] Waiting for Zambeze messages. To exit press CTRL+C')
    channel.start_consuming()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted')
        sys.exit(0)
