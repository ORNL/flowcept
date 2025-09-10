"""
This is a simple, standalone Redis consumer. Use it to customize to your needs or to use it as basis for other MQs.
"""
import redis
import msgpack

from flowcept.commons.daos.mq_dao.mq_dao_redis import MQDaoRedis
from flowcept.configs import MQ_HOST, MQ_PORT, MQ_CHANNEL, KVDB_URI
# Connect to Redis
redis_client = (
    redis.from_url(KVDB_URI) if KVDB_URI else redis.Redis(host=MQ_HOST, port=MQ_PORT, db=0)
)
# Subscribe to a channel
pubsub = redis_client.pubsub()
pubsub.subscribe(MQ_CHANNEL)

print("Listening for messages...")


for message in pubsub.listen():
    print()
    print("Received a message!", end=' ')
    if message and message["type"] in MQDaoRedis.MESSAGE_TYPES_IGNORE:
        continue

    if not isinstance(message["data"], (bytes, bytearray)):
        print(
            f"Skipping message with unexpected data type: {type(message["data"])} - {message["data"]}")
        continue

    try:
        msg_obj = msgpack.loads(message["data"], strict_map_key=False)
        msg_type = msg_obj.get("type", None)
        print(msg_type)
    except Exception as e:
        print(e)
