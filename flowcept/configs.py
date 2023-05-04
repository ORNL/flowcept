import os
import yaml
########################
#   Project Settings   #
########################

PROJECT_NAME = os.getenv("PROJECT_NAME", "flowcept")

PROJECT_DIR_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
SRC_DIR_PATH = os.path.join(PROJECT_DIR_PATH, PROJECT_NAME)

_settings_path = os.path.join(PROJECT_DIR_PATH, "resources", "settings.yaml")
SETTINGS_PATH = os.getenv("FLOWCEPT_SETTINGS_PATH", _settings_path)

with open(SETTINGS_PATH) as f:
    settings = yaml.safe_load(f)

########################
#   Log Settings       #
########################
LOG_FILE_PATH = settings["log"].get(
    "log_path", os.path.join(PROJECT_DIR_PATH, f"{PROJECT_NAME}.log")
)
# Possible values below are the typical python logging levels.
LOG_FILE_LEVEL = settings["log"].get("log_file_level", "debug").upper()
LOG_STREAM_LEVEL = settings["log"].get("log_stream_level", "debug").upper()

##########################
#  Experiment Settings   #
##########################

FLOWCEPT_USER = settings["experiment"].get("user", "blank_user")
EXPERIMENT_ID = settings["experiment"].get("experiment_id", "super-experiment")

######################
#   Redis Settings   #
######################
REDIS_HOST = settings["main_redis"].get("host", "localhost")
REDIS_PORT = int(settings["main_redis"].get("port", "6379"))
REDIS_CHANNEL = settings["main_redis"].get("channel", "interception")

######################
#  MongoDB Settings  #
######################
MONGO_HOST = settings["mongodb"].get("host", "localhost")
MONGO_PORT = int(settings["mongodb"].get("port", "27017"))
MONGO_DB = settings["mongodb"].get("db", "flowcept")
MONGO_COLLECTION = settings["mongodb"].get("collection", "tasks")
# In seconds:
MONGO_INSERTION_BUFFER_TIME = int(settings["mongodb"].get("insertion_buffer_time_secs", 5))
MONGO_INSERTION_BUFFER_SIZE = int(
    settings["mongodb"].get("insertion_buffer_size", 50)
)

DEBUG_MODE = settings["project"].get("debug", False)
JSON_SERIALIZER = settings["project"].get("json_serializer", "default")

######################
# EXTRA MSG METADATA #
######################
SYS_NAME = settings["extra_metadata"].get("sys_name", os.uname()[0])
NODE_NAME = settings["extra_metadata"].get("node_name", os.uname()[1])
# TODO: check login and user name later
LOGIN_NAME = settings["extra_metadata"].get("login_name", "login_name")

PUBLIC_IP = settings["extra_metadata"].get("public_ip", None)
PRIVATE_IP = settings["extra_metadata"].get("private_ip", None)


######################
#    Web Server      #
######################

WEBSERVER_HOST = settings["web_server"].get("host", "0.0.0.0")
WEBSERVER_PORT = int(settings["web_server"].get("port", "5000"))
