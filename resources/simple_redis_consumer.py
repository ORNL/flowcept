import redis
import msgpack
from flowcept.configs import MQ_HOST, MQ_PORT, MQ_CHANNEL

# Connect to Redis
redis_client = redis.Redis(host=MQ_HOST, port=MQ_PORT, db=0)

# Subscribe to a channel
pubsub = redis_client.pubsub()
pubsub.subscribe(MQ_CHANNEL)

print("Listening for messages...")


for message in pubsub.listen():
    print("Received a message!")
    if message["type"] in {"psubscribe"}:
        continue

    if isinstance(message["data"], int):
        message["data"] = str(message["data"]).encode()  # Convert to string and encode to bytes

    msg_obj = msgpack.loads(message["data"], strict_map_key=False)
    print(msg_obj)
