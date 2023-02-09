import os
import urllib.request
import socket
import getpass

########################
#   Project Settings   #
########################

PROJECT_NAME = os.getenv("PROJECT_NAME", "flowcept")

PROJECT_DIR_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
SRC_DIR_PATH = os.path.join(PROJECT_DIR_PATH, PROJECT_NAME)

_settings_path = os.path.join(PROJECT_DIR_PATH, "resources", "settings.yaml")
SETTINGS_PATH = os.getenv("SETTINGS_PATH", _settings_path)

########################
#   Log Settings       #
########################
LOG_FILE_PATH = os.getenv(
    "LOG_PATH", os.path.join(PROJECT_DIR_PATH, f"{PROJECT_NAME}.log")
)
# Possible values below are the typical python logging levels.
LOG_FILE_LEVEL = os.getenv("LOG_FILE_LEVEL", "debug").upper()
LOG_STREAM_LEVEL = os.getenv("LOG_STREAM_LEVEL", "debug").upper()

##########################
#  Experiment Settings   #
##########################

FLOWCEPT_USER = os.getenv("FLOWCEPT_USER", "root")
EXPERIMENT_ID = os.getenv("EXPERIMENT_ID", "super-experiment")

######################
#   Redis Settings   #
######################
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_CHANNEL = "interception"

######################
#  MongoDB Settings  #
######################
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "flowcept")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "messages")

# In seconds:
MONGO_INSERTION_BUFFER_TIME = int(os.getenv("MONGO_INSERTION_BUFFER_TIME", 5))
MONGO_INSERTION_BUFFER_SIZE = int(
    os.getenv("MONGO_INSERTION_BUFFER_SIZE", 50)
)

DEBUG_MODE = (
    True
    if os.getenv("DEBUG_MODE", "true").lower() in ["true", "yes", "y", 1]
    else False
)

######################
# EXTRA MSG METADATA #
######################
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


######################
#    Web Server      #
######################

WEBSERVER_HOST = os.getenv("WEBSERVER_HOST", "0.0.0.0")
WEBSERVER_PORT = int(os.getenv("WEBSERVER_PORT", "5000"))
