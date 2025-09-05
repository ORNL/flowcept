import inspect
from functools import wraps

from flowcept.flowcept_api.flowcept_controller import Flowcept


def flowcept(func=None, **flowcept_constructor_kwargs):
    """
    Usage:
        @flowcept
        def main(): ...

        @flowcept(project="X", campaign_id="C123", verbose=True)
        def main(): ...
    """

    def _decorate(f):
        is_async = inspect.iscoroutinefunction(f)
        flowcept_args = flowcept_constructor_kwargs.copy()
        flowcept_args["start_persistence"] = flowcept_constructor_kwargs.get("start_persistence", False)
        flowcept_args["save_workflow"] = flowcept_constructor_kwargs.get("save_workflow", False)
        flowcept_args["check_safe_stops"] = flowcept_constructor_kwargs.get("check_safe_stops", False)

        if is_async:

            @wraps(f)
            async def _aw(*args, **kwargs):
                # Flowcept used as a context manager around the coroutine call
                with Flowcept(**flowcept_args):
                    return await f(*args, **kwargs)

            return _aw
        else:

            @wraps(f)
            def _w(*args, **kwargs):
                with Flowcept(**flowcept_args):
                    return f(*args, **kwargs)

            return _w

    # Support bare @flowcept vs @flowcept(...)
    return _decorate if func is None else _decorate(func)
