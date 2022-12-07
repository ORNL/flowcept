import os

PROJECT_NAME = os.getenv("PROJECT_NAME", "flowcept")

PROJECT_DIR_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
SRC_DIR_PATH = os.path.join(PROJECT_DIR_PATH, PROJECT_NAME)

_settings_path = os.path.join(PROJECT_DIR_PATH, "resources", "settings.yaml")
SETTINGS_PATH = os.getenv("SETTINGS_PATH", _settings_path)

FLOWCEPT_USER = os.getenv("FLOWCEPT_USER", "flowcept_main_user")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CHANNEL = "interception"

MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "flowcept")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "messages")

# sec
MONGO_INSERTION_BUFFER_TIME = int(os.getenv("MONGO_INSERTION_BUFFER_TIME", 5))
MONGO_INSERTION_BUFFER_SIZE = int(
    os.getenv("MONGO_INSERTION_BUFFER_SIZE", 50)
)
