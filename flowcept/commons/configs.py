import os

settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                             "resources", "settings.yaml")
SETTINGS_PATH = os.getenv("SETTINGS_PATH", settings_path)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CHANNEL = "interception"
