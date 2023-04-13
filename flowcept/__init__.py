from flowcept.configs import PROJECT_NAME
from flowcept.version import __version__

from flowcept.flowcept_api.consumer_api import FlowceptConsumerAPI
from flowcept.flowcept_api.task_query_api import TaskQueryAPI

# TODO: Redo these try/excepts in a better way
try:
    from flowcept.flowceptor.plugins.zambeze.zambeze_interceptor import (
        ZambezeInterceptor,
    )
except:
    print("Could not import Zambeze Interceptor")
    pass

try:
    from flowcept.flowceptor.plugins.tensorboard.tensorboard_interceptor import (
        TensorboardInterceptor,
    )
except:
    print("Could not import TensorBoard interceptor.")

try:
    from flowcept.flowceptor.plugins.mlflow.mlflow_interceptor import (
        MLFlowInterceptor,
    )
except:
    print("Could not import MLFlow Interceptor")

try:
    from flowcept.flowceptor.plugins.dask.dask_plugins import (
        FlowceptDaskSchedulerPlugin,
        FlowceptDaskWorkerPlugin,
    )
except:
    print("Could not import Dask interceptor")
