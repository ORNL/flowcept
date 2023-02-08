from flowcept.commons.flowcept_logger import logger

try:
    logger.debug("debug")
    logger.info("info")
    logger.error("info")
    x = 2/0
except Exception as e:
    logger.exception(e)
    logger.info("It's ok")
