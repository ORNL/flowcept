import unittest

import flowcept.commons
from flowcept.commons.flowcept_logger import FlowceptLogger


class TestLog(unittest.TestCase):
    def test_log(self):
        _logger = FlowceptLogger()
        try:
            _logger.debug("debug")
            _logger.info("info")
            _logger.error("info")
            raise Exception("I want to test an exception raise!")
        except Exception as e:
            _logger.exception(e)
            _logger.info("It's ok")

        _logger2 = flowcept.commons.logger

        # Testing singleton
        assert id(_logger) == id(_logger2) == id(FlowceptLogger())
