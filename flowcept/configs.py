import os

PROJECT_NAME = os.getenv("PROJECT_NAME", "flowcept")

PROJECT_DIR_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
SRC_DIR_PATH = os.path.join(PROJECT_DIR_PATH, PROJECT_NAME)

_settings_path = os.path.join(PROJECT_DIR_PATH, "resources", "settings.yaml")
SETTINGS_PATH = os.getenv("SETTINGS_PATH", _settings_path)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CHANNEL = "interception"
