import os
import urllib.request
import socket
import getpass

PROJECT_NAME = os.getenv("PROJECT_NAME", "flowcept")

PROJECT_DIR_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
SRC_DIR_PATH = os.path.join(PROJECT_DIR_PATH, PROJECT_NAME)

_settings_path = os.path.join(PROJECT_DIR_PATH, "resources", "settings.yaml")
SETTINGS_PATH = os.getenv("SETTINGS_PATH", _settings_path)

FLOWCEPT_USER = os.getenv("FLOWCEPT_USER", "root")
EXPERIMENT_ID = os.getenv("EXPERIMENT_ID", "super-experiment")

# REDIS SETTINGS
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CHANNEL = "interception"

# MONGO SETTINGS
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "flowcept")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "messages")

# sec
MONGO_INSERTION_BUFFER_TIME = int(os.getenv("MONGO_INSERTION_BUFFER_TIME", 5))
MONGO_INSERTION_BUFFER_SIZE = int(
    os.getenv("MONGO_INSERTION_BUFFER_SIZE", 50)
)

DEBUG_MODE = (
    True
    if os.getenv("DEBUG_MODE", "true").lower() in ["true", "yes", "y", 1]
    else False
)

# EXTRA MSG METADATA
SYS_NAME = os.getenv("SYS_NAME", os.uname()[0])
NODE_NAME = os.getenv("NODE_NAME", os.uname()[1])
LOGIN_NAME = os.getenv("LOGIN_NAME", getpass.getuser())

try:
    external_ip = (
        urllib.request.urlopen("https://ident.me").read().decode("utf8")
    )
except Exception as e:
    print("Unable to retrieve external IP", e)
    external_ip = "unavailable"

PUBLIC_IP = os.getenv("PUBLIC_IP", external_ip)

PRIVATE_IP = os.getenv("PRIVATE_IP", socket.gethostbyname(socket.getfqdn()))
