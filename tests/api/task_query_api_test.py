import pytest

from flowcept.flowcept_api.task_query_api import TaskQueryAPI


def test_task_query_api_with_webserver_removed():
    with pytest.raises(RuntimeError, match="flowcept_webserver"):
        TaskQueryAPI(with_webserver=True)
