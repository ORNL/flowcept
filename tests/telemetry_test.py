import unittest
from flowcept.flowceptor.telemetry_capture import capture


class TestTelemetry(unittest.TestCase):
    def test_telemetry(self):
        telemetry = capture()
        assert telemetry.to_dict()
