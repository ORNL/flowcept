"""Interceptor module."""

from redis import Redis

from flowcept.commons.flowcept_dataclasses.base_settings_dataclasses import (
    BaseSettings,
)


class InterceptorStateManager(object):
    """Interceptor class."""

    def __init__(self, settings: BaseSettings):
        self._set_name = settings.key

        if not hasattr(settings, "redis_host"):
            raise Exception(
                f"This adapter setting {settings.key} manages state in Redis, so"
                f"Redis Host is required in the settings yaml file."
            )

        self._db = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=0,
        )

    def reset(self):
        """Reset it."""
        self._db.delete(self._set_name)

    def count(self):
        """Count it."""
        return self._db.scard(self._set_name)

    def add_element_id(self, element_id: str):
        """Add an element."""
        self._db.sadd(self._set_name, element_id)

    def has_element_id(self, element_id) -> bool:
        """Check for element."""
        return self._db.sismember(self._set_name, element_id)
