import unittest
from flowcept.commons.flowcept_logger import FlowceptLogger


class TestLog(unittest.TestCase):
    def test_log(self):
        _logger = FlowceptLogger().get_logger()
        try:
            _logger.debug("debug")
            _logger.info("info")
            _logger.error("info")
            raise Exception("I want to test an exception raise!")
        except Exception as e:
            _logger.exception(e)
            _logger.info("It's ok")

        _logger2 = FlowceptLogger().get_logger()

        # Testing singleton
        assert id(_logger) == id(_logger2)
