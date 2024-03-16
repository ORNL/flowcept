import unittest

from flowcept.flowceptor.telemetry_capture import TelemetryCapture


class TestTelemetry(unittest.TestCase):
    def test_telemetry(self):
        tele_capture = TelemetryCapture()
        telemetry = tele_capture.capture()
        assert telemetry.to_dict()
        tele_capture.shutdown_gpu_telemetry()
