"""Configuration module."""

import os
import socket
import getpass

from omegaconf import OmegaConf
import random

########################
#   Project Settings   #
########################

PROJECT_NAME = os.getenv("PROJECT_NAME", "flowcept")
SETTINGS_PATH = os.getenv("FLOWCEPT_SETTINGS_PATH", None)
SETTINGS_DIR = os.path.expanduser(f"~/.{PROJECT_NAME}")
if SETTINGS_PATH is None:
    SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.yaml")

if not os.path.exists(SETTINGS_PATH):
    raise Exception(
        f"Settings file {SETTINGS_PATH} was not found. "
        f"You should either define the "
        f"environment variable FLOWCEPT_SETTINGS_PATH with its path or "
        f"install Flowcept's package to create the directory "
        f"~/.flowcept with the file in it.\n"
        "A sample settings file is found in the 'resources' directory "
        "under the project's root path."
    )

settings = OmegaConf.load(SETTINGS_PATH)

########################
#   Log Settings       #
########################
LOG_FILE_PATH = settings["log"].get("log_path", "default")

if LOG_FILE_PATH == "default":
    LOG_FILE_PATH = os.path.join(SETTINGS_DIR, f"{PROJECT_NAME}.log")

# Possible values below are the typical python logging levels.
LOG_FILE_LEVEL = settings["log"].get("log_file_level", "debug").upper()
LOG_STREAM_LEVEL = settings["log"].get("log_stream_level", "debug").upper()

##########################
#  Experiment Settings   #
##########################

FLOWCEPT_USER = settings["experiment"].get("user", "blank_user")
CAMPAIGN_ID = settings["experiment"].get(
    "campaign_id", os.environ.get("CAMPAIGN_ID", "super_campaign")
)

######################
#   MQ Settings   #
######################
MQ_URI = settings["mq"].get("uri", None)
MQ_INSTANCES = settings["mq"].get("instances", None)

MQ_TYPE = os.getenv("MQ_TYPE", settings["mq"].get("type", "redis"))
MQ_CHANNEL = settings["mq"].get("channel", "interception")
MQ_PASSWORD = settings["mq"].get("password", None)
MQ_HOST = os.getenv("MQ_HOST", settings["mq"].get("host", "localhost"))
MQ_PORT = int(os.getenv("MQ_PORT", settings["mq"].get("port", "6379")))

MQ_BUFFER_SIZE = int(settings["mq"].get("buffer_size", 50))
MQ_INSERTION_BUFFER_TIME = int(settings["mq"].get("insertion_buffer_time_secs", 5))
MQ_INSERTION_BUFFER_TIME = random.randint(
    int(MQ_INSERTION_BUFFER_TIME * 0.9),
    int(MQ_INSERTION_BUFFER_TIME * 1.4),
)
MQ_CHUNK_SIZE = int(settings["mq"].get("chunk_size", -1))

#####################
# KV SETTINGS       #
#####################

KVDB_PASSWORD = settings["kv_db"].get("password", None)
KVDB_HOST = os.getenv("KVDB_HOST", settings["kv_db"].get("host", "localhost"))
KVDB_PORT = int(os.getenv("KVDB_PORT", settings["kv_db"].get("port", "6379")))


######################
#  MongoDB Settings  #
######################
MONGO_URI = settings["mongodb"].get("uri", os.environ.get("MONGO_URI", None))
MONGO_HOST = settings["mongodb"].get("host", os.environ.get("MONGO_HOST", "localhost"))
MONGO_PORT = int(settings["mongodb"].get("port", os.environ.get("MONGO_PORT", "27017")))
MONGO_DB = settings["mongodb"].get("db", PROJECT_NAME)
MONGO_CREATE_INDEX = settings["mongodb"].get("create_collection_index", True)

MONGO_TASK_COLLECTION = "tasks"
MONGO_WORKFLOWS_COLLECTION = "workflows"

# In seconds:
MONGO_INSERTION_BUFFER_TIME = int(settings["mongodb"].get("insertion_buffer_time_secs", 5))
MONGO_INSERTION_BUFFER_TIME = random.randint(
    int(MONGO_INSERTION_BUFFER_TIME * 0.9),
    int(MONGO_INSERTION_BUFFER_TIME * 1.4),
)

MONGO_ADAPTIVE_BUFFER_SIZE = settings["mongodb"].get("adaptive_buffer_size", True)
MONGO_MAX_BUFFER_SIZE = int(settings["mongodb"].get("max_buffer_size", 50))
MONGO_MIN_BUFFER_SIZE = max(1, int(settings["mongodb"].get("min_buffer_size", 10)))
MONGO_REMOVE_EMPTY_FIELDS = settings["mongodb"].get("remove_empty_fields", False)


######################
# PROJECT SYSTEM SETTINGS #
######################

DB_FLUSH_MODE = settings["project"].get("db_flush_mode", "online")
# DEBUG_MODE = settings["project"].get("debug", False)
PERF_LOG = settings["project"].get("performance_logging", False)
JSON_SERIALIZER = settings["project"].get("json_serializer", "default")
REPLACE_NON_JSON_SERIALIZABLE = settings["project"].get("replace_non_json_serializable", True)
ENRICH_MESSAGES = settings["project"].get("enrich_messages", True)
TELEMETRY_CAPTURE = settings["project"].get("telemetry_capture", None)

REGISTER_WORKFLOW = settings["project"].get("register_workflow", True)

##################################
# GPU TELEMETRY CAPTURE SETTINGS #
#################################

#  TODO: This is legacy. We should improve the way to set these
#   initial variables and initialize GPU libs.
#   We could move this to the static part of TelemetryCapture
N_GPUS = dict()
GPU_HANDLES = None
if TELEMETRY_CAPTURE is not None and TELEMETRY_CAPTURE.get("gpu", None) is not None:
    if eval(TELEMETRY_CAPTURE.get("gpu", "None")) is not None:
        try:
            visible_devices_var = os.environ.get("CUDA_VISIBLE_DEVICES", None)
            if visible_devices_var is not None:
                visible_devices = [int(i) for i in visible_devices_var.split(",")]
                if len(visible_devices):
                    N_GPUS["nvidia"] = visible_devices
                    GPU_HANDLES = []  # TODO
            else:
                from pynvml import nvmlDeviceGetCount

                N_GPUS["nvidia"] = list(range(0, nvmlDeviceGetCount()))
                GPU_HANDLES = []
        except Exception:
            pass
        try:
            visible_devices_var = os.environ.get("ROCR_VISIBLE_DEVICES", None)
            if visible_devices_var is not None:
                visible_devices = [int(i) for i in visible_devices_var.split(",")]
                if len(visible_devices):
                    N_GPUS["amd"] = visible_devices
                    from amdsmi import (
                        amdsmi_init,
                        amdsmi_get_processor_handles,
                    )

                    amdsmi_init()
                    GPU_HANDLES = amdsmi_get_processor_handles()
            else:
                from amdsmi import amdsmi_init, amdsmi_get_processor_handles

                amdsmi_init()
                GPU_HANDLES = amdsmi_get_processor_handles()
                N_GPUS["amd"] = list(range(0, len(GPU_HANDLES)))
        except Exception:
            pass

if len(N_GPUS.get("amd", [])):
    GPU_TYPE = "amd"
elif len(N_GPUS.get("nvidia", [])):
    GPU_TYPE = "nvidia"
else:
    GPU_TYPE = None

######################
# SYS METADATA #
######################

LOGIN_NAME = None
PUBLIC_IP = None
PRIVATE_IP = None
SYS_NAME = None
NODE_NAME = None
ENVIRONMENT_ID = None

sys_metadata = settings.get("sys_metadata", None)
if sys_metadata is not None:
    ENVIRONMENT_ID = sys_metadata.get("environment_id", None)
    SYS_NAME = sys_metadata.get("sys_name", None)
    NODE_NAME = sys_metadata.get("node_name", None)
    LOGIN_NAME = sys_metadata.get("login_name", None)
    PUBLIC_IP = sys_metadata.get("public_ip", None)
    PRIVATE_IP = sys_metadata.get("private_ip", None)


if LOGIN_NAME is None:
    try:
        LOGIN_NAME = sys_metadata.get("login_name", getpass.getuser())
    except Exception:
        try:
            LOGIN_NAME = os.getlogin()
        except Exception:
            LOGIN_NAME = None

SYS_NAME = SYS_NAME if SYS_NAME is not None else os.uname()[0]
NODE_NAME = NODE_NAME if NODE_NAME is not None else os.uname()[1]

try:
    HOSTNAME = socket.getfqdn()
except Exception:
    try:
        HOSTNAME = socket.gethostname()
    except Exception:
        try:
            with open("/etc/hostname", "r") as f:
                HOSTNAME = f.read().strip()
        except Exception:
            HOSTNAME = "unknown_hostname"


EXTRA_METADATA = settings.get("extra_metadata", {})
EXTRA_METADATA.update({"mq_host": MQ_HOST})
EXTRA_METADATA.update({"mq_port": MQ_PORT})

######################
#    Web Server      #
######################

_webserver_settings = settings.get("web_server", {})
WEBSERVER_HOST = _webserver_settings.get("host", "0.0.0.0")
WEBSERVER_PORT = int(_webserver_settings.get("port", 5000))

######################
#    ANALYTICS      #
######################

ANALYTICS = settings.get("analytics", None)


####

INSTRUMENTATION = settings.get("instrumentation", None)
INSTRUMENTATION_ENABLED = False
if INSTRUMENTATION:
    INSTRUMENTATION_ENABLED = INSTRUMENTATION.get("enabled", False)

################# Enabled ADAPTERS

ADAPTERS = set()

for adapter in settings.get("adapters", set()):
    ADAPTERS.add(settings["adapters"][adapter].get("kind"))
