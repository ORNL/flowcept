from flowcept.commons.flowcept_logger import FlowceptLogger

_logger = FlowceptLogger().logger
try:
    _logger.debug("debug")
    _logger.info("info")
    _logger.error("info")
    x = 2 / 0
except Exception as e:
    _logger.exception(e)
    _logger.info("It's ok")

_logger2 = FlowceptLogger().logger

assert id(_logger) == id(_logger2)
