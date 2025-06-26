"""Key value module."""

from flowcept.commons.daos.redis_conn import RedisConn

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import (
    KVDB_HOST,
    KVDB_PORT,
    KVDB_PASSWORD,
    KVDB_URI,
)


class KeyValueDAO:
    """Key value DAO class."""

    _instance: "KeyValueDAO" = None

    def __new__(cls, *args, **kwargs) -> "KeyValueDAO":
        """Singleton creator for KeyValueDAO."""
        # Check if an instance already exists
        if cls._instance is None:
            # Create a new instance if not
            cls._instance = super(KeyValueDAO, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self.logger = FlowceptLogger()
            self.redis_conn = RedisConn.build_redis_conn_pool(
                host=KVDB_HOST, port=KVDB_PORT, password=KVDB_PASSWORD, uri=KVDB_URI
            )

    def delete_set(self, set_name: str):
        """Delete it."""
        self.redis_conn.delete(set_name)

    def add_key_into_set(self, set_name: str, key):
        """Add a key."""
        self.redis_conn.sadd(set_name, key)

    def remove_key_from_set(self, set_name: str, key):
        """Remove a key."""
        self.logger.debug(f"Removing key {key} from set: {set_name}")
        self.redis_conn.srem(set_name, key)
        self.logger.debug(f"Removed key {key} from set: {set_name}")

    def set_has_key(self, set_name: str, key) -> bool:
        """Set the key."""
        return self.redis_conn.sismember(set_name, key)

    def set_count(self, set_name: str):
        """Set the count."""
        return self.redis_conn.scard(set_name)

    def set_is_empty(self, set_name: str) -> bool:
        """Set as empty."""
        _count = self.set_count(set_name)
        self.logger.info(f"Set {set_name} has {_count}")
        return _count == 0

    def delete_all_matching_sets(self, key_pattern):
        """Delete matching sets."""
        matching_sets = self.redis_conn.keys(key_pattern)
        for set_name in matching_sets:
            self.delete_set(set_name)

    def set_key_value(self, key, value):
        """
        Store a key-value pair in Redis.

        Parameters
        ----------
        key : str
            The key to store in Redis.
        value : str
            The value associated with the key.

        Returns
        -------
        None
        """
        self.redis_conn.set(key, value)

    def get_key(self, key):
        """
        Retrieve a value from Redis by key.

        Parameters
        ----------
        key : str
            The key to look up in Redis.

        Returns
        -------
        str or None
            The decoded value if the key exists, otherwise None.
        """
        value = self.redis_conn.get(key)
        return value.decode() if value else None

    def delete_key(self, key):
        """
        Delete the key if it exists.

        Parameters
        ----------
        key : str
            The key to look up in Redis.

        Returns
        -------
        None
        """
        self.redis_conn.delete(key)

    def liveness_test(self):
        """Get the livelyness of it."""
        try:
            response = self.redis_conn.ping()
            if response:
                return True
            else:
                return False
        except ConnectionError as e:
            self.logger.exception(e)
            return False
        except Exception as e:
            self.logger.exception(e)
            return False
