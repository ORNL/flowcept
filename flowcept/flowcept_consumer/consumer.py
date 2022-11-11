import sys
import redis
from flowcept.configs import REDIS_PORT, REDIS_HOST, REDIS_CHANNEL


def send_to_service(message):
    # TODO: implement
    print(message)
    pass


def consume_intercepted_messages():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    p = r.pubsub()
    p.psubscribe(REDIS_CHANNEL)
    print(f"Subscribed to {REDIS_CHANNEL}. Waiting for messages.")
    for message in p.listen():
        if message["type"] in {"psubscribe"}:  # TODO make it a constant
            continue
        print(
            f"I'm a Flowceptor consumer and I received this message:"
            f""
            f"\n\t{message}"
        )
        send_to_service(message)


if __name__ == "__main__":
    try:
        consume_intercepted_messages()
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(0)
