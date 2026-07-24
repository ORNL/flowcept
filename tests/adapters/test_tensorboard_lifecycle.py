from types import SimpleNamespace
from unittest.mock import patch

import pytest

tensorboard_module = pytest.importorskip("flowcept.flowceptor.adapters.tensorboard.tensorboard_interceptor")
TensorboardInterceptor = tensorboard_module.TensorboardInterceptor


def _noop(*_args, **_kwargs):
    pass


def test_stop_joins_observer_before_final_callback():
    events = []
    interceptor = TensorboardInterceptor.__new__(TensorboardInterceptor)
    interceptor._observer = SimpleNamespace(
        stop=lambda: events.append("stop"),
        join=lambda: events.append("join"),
    )
    interceptor.callback = lambda: events.append("callback")
    interceptor.logger = SimpleNamespace(debug=_noop, exception=_noop)
    interceptor._interceptor_instance_id = "test-interceptor"
    interceptor._bundle_exec_id = "test-bundle"
    interceptor._mq_dao = SimpleNamespace(stop=lambda **_kwargs: events.append("mq_stop"))

    with patch.object(tensorboard_module, "sleep", _noop):
        assert TensorboardInterceptor.stop(interceptor, check_safe_stops=False)

    assert events == ["stop", "join", "callback", "mq_stop"]
    assert interceptor._observer is None
