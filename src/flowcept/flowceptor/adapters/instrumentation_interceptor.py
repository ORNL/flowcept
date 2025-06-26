"""Instrumentation Insterceptor."""

from flowcept.flowceptor.adapters.base_interceptor import (
    BaseInterceptor,
)


# TODO: :base-interceptor-refactor: :ml-refactor: :code-reorg:
class InstrumentationInterceptor:
    """Interceptor class."""

    _instance: "BaseInterceptor" = None

    def __new__(cls, *args, **kwargs):
        """Construct method, which should not be used. Use get_instance instead."""
        raise Exception("Please utilize the InstrumentationInterceptor.get_instance method.")

    @classmethod
    def get_instance(cls):
        """Get instance method for this singleton."""
        if not cls._instance:
            cls._instance = BaseInterceptor(kind="instrumentation")
        return cls._instance
