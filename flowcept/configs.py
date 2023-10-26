import os
import socket

import yaml
import random

########################
#   Project Settings   #
########################

PROJECT_NAME = os.getenv("PROJECT_NAME", "flowcept")
SETTINGS_PATH = os.getenv("FLOWCEPT_SETTINGS_PATH", None)
if SETTINGS_PATH is None:
    project_dir_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    SETTINGS_PATH = os.path.join(
        project_dir_path, "resources", "settings.yaml"
    )

if not os.path.isabs(SETTINGS_PATH):
    # TODO: check if we really need abs path
    raise Exception("Please use an absolute path for the settings.yaml")


with open(SETTINGS_PATH) as f:
    settings = yaml.safe_load(f)

########################
#   Log Settings       #
########################
LOG_FILE_PATH = settings["log"].get("log_path", f"{PROJECT_NAME}.log")

# Possible values below are the typical python logging levels.
LOG_FILE_LEVEL = settings["log"].get("log_file_level", "debug").upper()
LOG_STREAM_LEVEL = settings["log"].get("log_stream_level", "debug").upper()

##########################
#  Experiment Settings   #
##########################

FLOWCEPT_USER = settings["experiment"].get("user", "blank_user")
CAMPAIGN_ID = settings["experiment"].get("campaign_id", "super_campaign")

######################
#   Redis Settings   #
######################
REDIS_HOST = settings["main_redis"].get("host", "localhost")
REDIS_PORT = int(settings["main_redis"].get("port", "6379"))
REDIS_CHANNEL = settings["main_redis"].get("channel", "interception")
REDIS_PASSWORD = settings["main_redis"].get("password", None)
REDIS_STARTED_MQ_THREADS_KEY = "started_mq_threads"
REDIS_BUFFER_SIZE = int(settings["main_redis"].get("buffer_size", 50))
REDIS_INSERTION_BUFFER_TIME = int(
    settings["main_redis"].get("insertion_buffer_time_secs", 5)
)
REDIS_INSERTION_BUFFER_TIME = random.randint(
    int(REDIS_INSERTION_BUFFER_TIME * 0.9),
    int(REDIS_INSERTION_BUFFER_TIME * 1.4),
)

######################
#  MongoDB Settings  #
######################
MONGO_HOST = settings["mongodb"].get("host", "localhost")
MONGO_PORT = int(settings["mongodb"].get("port", "27017"))
MONGO_DB = settings["mongodb"].get("db", "flowcept")

MONGO_TASK_COLLECTION = "tasks"
MONGO_WORKFLOWS_COLLECTION = "workflows"


# In seconds:
MONGO_INSERTION_BUFFER_TIME = int(
    settings["mongodb"].get("insertion_buffer_time_secs", 5)
)
MONGO_INSERTION_BUFFER_TIME = random.randint(
    int(MONGO_INSERTION_BUFFER_TIME * 0.9),
    int(MONGO_INSERTION_BUFFER_TIME * 1.4),
)

MONGO_ADAPTIVE_BUFFER_SIZE = settings["mongodb"].get(
    "adaptive_buffer_size", True
)
MONGO_MAX_BUFFER_SIZE = int(settings["mongodb"].get("max_buffer_size", 50))
MONGO_MIN_BUFFER_SIZE = max(
    1, int(settings["mongodb"].get("min_buffer_size", 10))
)
MONGO_REMOVE_EMPTY_FIELDS = settings["mongodb"].get(
    "remove_empty_fields", False
)


######################
# SYSTEM SETTINGS #
######################

MQ_TYPE = settings["project"].get("mq_type", "redis")
DEBUG_MODE = settings["project"].get("debug", False)
PERF_LOG = settings["project"].get("performance_logging", False)
JSON_SERIALIZER = settings["project"].get("json_serializer", "default")
TELEMETRY_CAPTURE = settings["project"].get("telemetry_capture", None)

######################
# SYS METADATA #
######################

sys_metadata = settings.get("sys_metadata", None)
if sys_metadata is not None:
    SYS_NAME = sys_metadata.get("sys_name", os.uname()[0])
    NODE_NAME = sys_metadata.get("node_name", os.uname()[1])
    LOGIN_NAME = sys_metadata.get("login_name", "login_name")
    PUBLIC_IP = sys_metadata.get("public_ip", None)
    PRIVATE_IP = sys_metadata.get("private_ip", None)
else:
    SYS_NAME = os.uname()[0]
    NODE_NAME = os.uname()[1]
    LOGIN_NAME = None
    PUBLIC_IP = None
    PRIVATE_IP = None

try:
    HOSTNAME = socket.getfqdn()
except:
    try:
        HOSTNAME = socket.gethostname()
    except:
        try:
            with open("/etc/hostname", "r") as f:
                HOSTNAME = f.read().strip()
        except:
            HOSTNAME = "unknown_hostname"


EXTRA_METADATA = settings.get("extra_metadata", None)

######################
#    Web Server      #
######################

WEBSERVER_HOST = settings["web_server"].get("host", "0.0.0.0")
WEBSERVER_PORT = int(settings["web_server"].get("port", "5000"))
