import sys
import redis

from flowcept.commons.configs import REDIS_PORT, REDIS_HOST, REDIS_CHANNEL


def send_to_service(message):
    print("Received message:")
    print(message)

def main():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    p = r.pubsub()
    p.psubscribe(REDIS_CHANNEL)
    print(f"Subscribed to {REDIS_CHANNEL}. Waiting for messages.")
    for new_message in p.listen():
        send_to_service(new_message)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted')
        sys.exit(0)
