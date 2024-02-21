from flowcept.commons.utils import get_adapter_exception_msg
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor

logger = FlowceptLogger()

# TODO :base-interceptor-refactor: :ml-refactor: :code-reorg: :usability:
#  Consider creating a new concept for instrumentation-based 'interception'.
#  These adaptors were made for data observability.
#  Perhaps we should have a BaseAdaptor that would work for both and
#  observability and instrumentation adapters. This would be a major refactor
#  in the code. https://github.com/ORNL/flowcept/issues/109
instrumentation_interceptor = BaseInterceptor(plugin_key=None)
instrumentation_interceptor._registered_workflow = True
# TODO This above is bad because I am reusing the same BaseInterceptor both
#  for adapter-based observability + traditional instrumentation via @decorator
