from abc import ABCMeta
from redis import Redis

from flowcept.flowceptor.plugins.abstract_flowceptor import AbstractFlowceptor


class AbstractInterceptorStateManager(object, metaclass=ABCMeta):
    def __init__(self, plugin_key: str):
        self.set_name = plugin_key
        settings = AbstractFlowceptor.get_settings(plugin_key)
        if not hasattr(settings, "redis_host"):
            raise Exception(
                f"This plugin setting {plugin_key} "
                f"does not have a Redis Host."
            )

        self._db = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=0,
        )

    def clear_set(self):
        self._db.delete(self.set_name)

    def add_element_id(self, element_id: str):
        self._db.sadd(self.set_name, element_id)

    def has_element_id(self, element_id) -> bool:
        return self._db.sismember(self.set_name, element_id)
