import os

PROJECT_DIR_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

_settings_path = os.path.join(PROJECT_DIR_PATH, "resources", "settings.yaml")
SETTINGS_PATH = os.getenv("SETTINGS_PATH", _settings_path)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CHANNEL = "interception"
