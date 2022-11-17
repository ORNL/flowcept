from redis import Redis

from flowcept.flowceptor.plugins.settings_dataclasses import AbstractSettings


class InterceptorStateManager(object):
    def __init__(self, settings: AbstractSettings):
        self._set_name = settings.key

        if not hasattr(settings, "redis_host"):
            raise Exception(
                f"This plugin setting {settings.key} "
                f"does not have a Redis Host."
            )

        self._db = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=0,
        )

    def clear_set(self):
        self._db.delete(self._set_name)

    def add_element_id(self, element_id: str):
        self._db.sadd(self._set_name, element_id)

    def has_element_id(self, element_id) -> bool:
        return self._db.sismember(self._set_name, element_id)
