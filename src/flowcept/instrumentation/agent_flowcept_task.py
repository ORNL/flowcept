"""Task module."""

import threading
from time import time
from functools import wraps
import argparse
from typing import Dict

from flowcept.commons.flowcept_dataclasses.task_object import (
    TaskObject,
)
from flowcept.commons.vocabulary import Status
from flowcept.commons.flowcept_logger import FlowceptLogger

from flowcept.commons.utils import replace_non_serializable
from flowcept.configs import (
    REPLACE_NON_JSON_SERIALIZABLE,
    INSTRUMENTATION_ENABLED,
)
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor
from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager
from langchain_core.language_models import LLM

_thread_local = threading.local()


# TODO: :code-reorg: consider moving it to utils and reusing it in dask interceptor
def default_args_handler(*args, **kwargs):
    """Get default arguments."""
    args_handled = {}
    if args is not None and len(args):
        if isinstance(args[0], argparse.Namespace):
            args_handled.update(args[0].__dict__)
            args = args[1:]
        for i in range(len(args)):
            args_handled[f"arg_{i}"] = args[i]
    if kwargs is not None and len(kwargs):
        args_handled.update(kwargs)
    if REPLACE_NON_JSON_SERIALIZABLE:
        args_handled = replace_non_serializable(args_handled)
    return args_handled


def agent_flowcept_task(func=None, **decorator_kwargs):
    """Get flowcept task."""
    if INSTRUMENTATION_ENABLED:
        interceptor = InstrumentationInterceptor.get_instance()
        logger = FlowceptLogger()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not INSTRUMENTATION_ENABLED:
                return func(*args, **kwargs)

            args_handler = decorator_kwargs.get("args_handler", default_args_handler)
            custom_metadata = decorator_kwargs.get("custom_metadata", None)
            tags = decorator_kwargs.get("tags", None)

            task_obj = TaskObject()
            task_obj.subtype = decorator_kwargs.get("subtype", "agent_task")
            task_obj.activity_id = func.__name__
            handled_args = args_handler(*args, **kwargs)
            task_obj.workflow_id = handled_args.pop("workflow_id", Flowcept.current_workflow_id)
            task_obj.campaign_id = handled_args.pop("campaign_id", Flowcept.campaign_id)
            task_obj.used = handled_args
            task_obj.tags = tags
            task_obj.started_at = time()
            task_obj.custom_metadata = custom_metadata or {}
            task_obj.task_id = str(task_obj.started_at)
            _thread_local._flowcept_current_context_task_id = task_obj.task_id
            task_obj.telemetry_at_start = interceptor.telemetry_capture.capture()
            task_obj.agent_id = BaseAgentContextManager.agent_id

            try:
                result = func(*args, **kwargs)
                task_obj.status = Status.FINISHED
            except Exception as e:
                task_obj.status = Status.ERROR
                result = None
                logger.exception(e)
                task_obj.stderr = str(e)
            task_obj.ended_at = time()

            task_obj.telemetry_at_end = interceptor.telemetry_capture.capture()
            try:
                if result is not None:
                    if isinstance(result, dict):
                        task_obj.generated = {}
                        if "llm" in result:
                            llm = result.pop("llm")
                            # TODO: assert type

                            task_obj.custom_metadata["llm"] = _extract_llm_metadata(llm)
                        if "prompt" in result:
                            parsed_prompt = [{"role": msg.type, "content": msg.content} for msg in result.pop("prompt")]
                            task_obj.custom_metadata["prompt"] = parsed_prompt
                        if "response" in result:
                            task_obj.custom_metadata["llm_response"] = result.pop("response")
                        task_obj.generated.update(args_handler(**result))
                    else:
                        task_obj.generated = args_handler(result)
            except Exception as e:
                logger.exception(e)

            interceptor.intercept(task_obj.to_dict())
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def get_current_context_task_id():
    """Retrieve the current task object from thread-local storage."""
    return getattr(_thread_local, "_flowcept_current_context_task_id", None)

def _extract_llm_metadata(llm: LLM) -> Dict:
    """
    Extract metadata from a LangChain LLM instance.

    Parameters
    ----------
    llm : LLM
        The language model instance.

    Returns
    -------
    dict
        Dictionary containing class name, module, model name, and configuration if available.
    """
    llm_metadata = {
        "class_name": llm.__class__.__name__,
        "module": llm.__class__.__module__,
        "config": llm.dict() if hasattr(llm, "dict") else {},
    }
    return llm_metadata
