"""Task module."""

import threading
from time import time
from functools import wraps
import argparse
from typing import Dict, Any, Union

from crewai import BaseLLM

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
from flowcept.instrumentation.task_capture import FlowceptTask
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
            _thread_local._flowcept_current_context_task = task_obj
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
                        task_obj.generated = args_handler(**result)
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


def get_current_context_task() -> TaskObject | None:
    """Retrieve the current task object from thread-local storage."""
    return getattr(_thread_local, "_flowcept_current_context_task", None)

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


from typing import Any, Optional, List, Dict
from langchain_core.language_models import LLM
from langchain_core.messages import BaseMessage


from langchain_core.runnables import Runnable
from langchain_core.language_models.base import BaseLanguageModel


class FlowceptLLM(BaseLLM, Runnable):

    def __init__(self, llm: BaseLanguageModel, agent_id: str = None, parent_task_id:str=None, workflow_id=None, campaign_id=None):
        self.llm = llm
        self.agent_id = agent_id
        self.worflow_id = workflow_id
        self.campaign_id = campaign_id
        self.metadata = _extract_llm_metadata(llm)
        self.parent_task_id = parent_task_id

    def _our_call(self, messages, **kwargs):
        messages_str = FlowceptLLM._format_messages(messages)
        used = {"prompt": messages_str}
        with FlowceptTask(used=used,
                          subtype="llm_task",
                          custom_metadata=self.metadata,
                          agent_id=self.agent_id,
                          activity_id="llm_interaction",
                          campaign_id=self.campaign_id,
                          workflow_id=self.worflow_id,
                          parent_task_id=self.parent_task_id) as task:
            response = self.llm.invoke(messages, **kwargs)
            response_str = response.content if isinstance(response, BaseMessage) else str(response)
            generated = {"response": response_str}

            if hasattr(response, "response_metadata"):
                task._task.custom_metadata["response_metadata"] = response.response_metadata

            task.end(generated=generated)
            return response_str

    def call(
            self,
            messages: Union[str, List[Dict[str, str]]],
            tools: Optional[List[dict]] = None,
            callbacks: Optional[List[Any]] = None,
            available_functions: Optional[Dict[str, Any]] = None,
    ) -> Union[str, Any]:
        return self._our_call(messages)

    def invoke(self, input: Union[str, List[Dict[str, str]]], **kwargs) -> Any:
        """Used by LangChain"""
        return self._our_call(input, **kwargs)

    def __call__(self, *args, **kwargs):
        return self.invoke(*args, **kwargs)

    @staticmethod
    def _format_messages(messages: Union[str, List[Dict[str, str]]]) -> str:
        if isinstance(messages, str):
            return messages
        elif isinstance(messages, list):
            return "\n".join(
                f"{m.get('role', '').capitalize()}: {m.get('content', '')}" for m in messages
            )
        else:
            raise ValueError(f"Invalid message format: {messages}")
