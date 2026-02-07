import unittest

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.telemetry_capture import TelemetryCapture


class TestTelemetry(unittest.TestCase):
    def test_telemetry(self):
        tele_capture = TelemetryCapture()
        telemetry = tele_capture.capture()
        if telemetry is None:
            FlowceptLogger().warning(
                "Skipping telemetry test because telemetry capture is disabled in settings."
            )
            self.skipTest("Telemetry capture disabled.")
        assert telemetry.to_dict()
        tele_capture.shutdown_gpu_telemetry()
