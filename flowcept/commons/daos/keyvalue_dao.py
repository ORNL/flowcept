from redis import Redis

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons import singleton
from flowcept.configs import (
    KVDB_HOST,
    KVDB_PORT,
    KVDB_PASSWORD,
)


@singleton
class KeyValueDAO:
    def __init__(self, connection=None):
        self.logger = FlowceptLogger()
        if connection is None:
            self._redis = Redis(
                host=KVDB_HOST,
                port=KVDB_PORT,
                db=0,
                password=KVDB_PASSWORD,
            )
        else:
            self._redis = connection

    def delete_set(self, set_name: str):
        self._redis.delete(set_name)

    def add_key_into_set(self, set_name: str, key):
        self._redis.sadd(set_name, key)

    def remove_key_from_set(self, set_name: str, key):
        self.logger.debug(f"Removing key {key} from set: {set_name}")
        self._redis.srem(set_name, key)
        self.logger.debug(f"Removed key {key} from set: {set_name}")

    def set_has_key(self, set_name: str, key) -> bool:
        return self._redis.sismember(set_name, key)

    def set_count(self, set_name: str):
        return self._redis.scard(set_name)

    def set_is_empty(self, set_name: str) -> bool:
        _count = self.set_count(set_name)
        self.logger.info(f"Set {set_name} has {_count}")
        return _count == 0

    def delete_all_matching_sets(self, key_pattern):
        matching_sets = self._redis.keys(key_pattern)
        for set_name in matching_sets:
            self.delete_set(set_name)
