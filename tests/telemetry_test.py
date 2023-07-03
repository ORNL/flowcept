import unittest
import json

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.telemetry_capture import capture_telemetry


class TestTelemetry(unittest.TestCase):
    def test_telemetry(self):
        self.logger = FlowceptLogger().get_logger()
        telemetry = capture_telemetry(self.logger)
        assert telemetry.to_dict()
        print(json.dumps(telemetry.to_dict(), indent=True))
