import unittest
from flowcept.flowceptor.telemetry_capture import capture_telemetry


class TestTelemetry(unittest.TestCase):
    def test_telemetry(self):
        telemetry = capture_telemetry()
        assert telemetry.to_dict()
