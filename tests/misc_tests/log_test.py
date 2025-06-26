import logging
import os.path
import unittest

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import PROJECT_NAME, LOG_FILE_LEVEL, LOG_FILE_PATH


class TestLog(unittest.TestCase):
    def test_log(self):
        _logger = FlowceptLogger()
        try:
            _logger.debug("debug")
            _logger.info("info")
            _logger.error("info")
            _logger.critical("aaaaa")
            raise Exception("I want to test an exception raise!")
        except Exception as e:
            _logger.exception(e)
            _logger.info("It's ok")

        _logger2 = FlowceptLogger()

        # Testing singleton
        assert (
            id(_logger)
            == id(_logger2)
            == id(FlowceptLogger())
            == id(logging.getLogger(PROJECT_NAME))
        )

        self.assertIs(_logger, _logger2)
        _logger.v = "test_val"
        self.assertEqual(_logger2.v, "test_val")
