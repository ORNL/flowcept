import json
from redis import Redis
from redis.client import PubSub

from flowcept.configs import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_CHANNEL,
)


class MQDao:
    def __init__(self):
        self._redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

    def subscribe(self) -> PubSub:
        pubsub = self._redis.pubsub()
        pubsub.psubscribe(REDIS_CHANNEL)
        return pubsub

    def publish(self, json_formatted_str_message: str):
        self._redis.publish(
            REDIS_CHANNEL, json.dumps(json_formatted_str_message)
        )
