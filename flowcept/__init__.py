from flowcept.configs import PROJECT_NAME
from flowcept.version import __version__

from flowcept.flowcept_api.consumer_api import FlowceptConsumerAPI
from flowcept.flowcept_api.task_query_api import TaskQueryAPI

try:
    from flowcept.flowceptor.plugins.zambeze.zambeze_interceptor import (
        ZambezeInterceptor,
    )
except:
    pass

try:
    from flowcept.flowceptor.plugins.tensorboard.tensorboard_interceptor import (
        TensorboardInterceptor,
    )
except:
    pass

try:
    from flowcept.flowceptor.plugins.mlflow.mlflow_interceptor import (
        MLFlowInterceptor,
    )
except:
    pass

try:
    from flowcept.flowceptor.plugins.dask.dask_plugins import (
        FlowceptDaskSchedulerPlugin,
        FlowceptDaskWorkerPlugin,
    )
except:
    pass

# from flowcept.flowceptor.decorators.responsible_ai import (
#     model_explainer,
#     model_profiler,
# )

from flowcept.flowcept_api import db_api
