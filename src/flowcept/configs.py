"""Configuration module."""

import os
import socket
import getpass

from flowcept.version import __version__

PROJECT_NAME = "flowcept"

DEFAULT_SETTINGS = {
    "version": __version__,
    "log": {"log_file_level": "disable", "log_stream_level": "disable"},
    "project": {"dump_buffer_path": "flowcept_messages.jsonl"},
    "telemetry_capture": {},
    "instrumentation": {},
    "experiment": {},
    "mq": {"enabled": False},
    "kv_db": {"enabled": False},
    "web_server": {},
    "sys_metadata": {},
    "extra_metadata": {},
    "analytics": {},
    "db_buffer": {},
    "databases": {"mongodb": {"enabled": False}, "lmdb": {"enabled": False}},
    "adapters": {},
    "agent": {},
}

USE_DEFAULT = os.getenv("FLOWCEPT_USE_DEFAULT", "False").lower() == "true"

if USE_DEFAULT:
    settings = DEFAULT_SETTINGS.copy()

else:
    from omegaconf import OmegaConf

    _SETTINGS_DIR = os.path.expanduser(f"~/.{PROJECT_NAME}")
    SETTINGS_PATH = os.getenv("FLOWCEPT_SETTINGS_PATH", f"{_SETTINGS_DIR}/settings.yaml")

    if not os.path.exists(SETTINGS_PATH):
        from importlib import resources

        SETTINGS_PATH = str(resources.files("resources").joinpath("sample_settings.yaml"))

        with open(SETTINGS_PATH) as f:
            settings = OmegaConf.load(f)
    else:
        settings = OmegaConf.load(SETTINGS_PATH)

# Making sure all settings are in place.
keys = DEFAULT_SETTINGS.keys() - settings.keys()
if len(keys):
    for k in keys:
        settings[k] = DEFAULT_SETTINGS[k]

########################
#   Log Settings       #
########################

LOG_FILE_PATH = settings["log"].get("log_path", "default")

if LOG_FILE_PATH == "default":
    LOG_FILE_PATH = f"{PROJECT_NAME}.log"

# Possible values below are the typical python logging levels.
LOG_FILE_LEVEL = settings["log"].get("log_file_level", "disable").upper()
LOG_STREAM_LEVEL = settings["log"].get("log_stream_level", "disable").upper()

##########################
#  Experiment Settings   #
##########################

FLOWCEPT_USER = settings["experiment"].get("user", "blank_user")

######################
#   MQ Settings   #
######################

MQ_INSTANCES = settings["mq"].get("instances", None)
MQ_SETTINGS = settings["mq"]
MQ_ENABLED = os.getenv("MQ_ENABLED", settings["mq"].get("enabled", True))
MQ_TYPE = os.getenv("MQ_TYPE", settings["mq"].get("type", "redis"))
MQ_CHANNEL = os.getenv("MQ_CHANNEL", settings["mq"].get("channel", "interception"))
MQ_PASSWORD = settings["mq"].get("password", None)
MQ_HOST = os.getenv("MQ_HOST", settings["mq"].get("host", "localhost"))
MQ_PORT = int(os.getenv("MQ_PORT", settings["mq"].get("port", "6379")))
MQ_URI = os.getenv("MQ_URI", settings["mq"].get("uri", None))
MQ_BUFFER_SIZE = settings["mq"].get("buffer_size", None)
MQ_INSERTION_BUFFER_TIME = settings["mq"].get("insertion_buffer_time_secs", None)
MQ_TIMING = settings["mq"].get("timing", False)
MQ_CHUNK_SIZE = int(settings["mq"].get("chunk_size", -1))

#####################
# KV SETTINGS       #
#####################

KVDB_PASSWORD = settings["kv_db"].get("password", None)
KVDB_HOST = os.getenv("KVDB_HOST", settings["kv_db"].get("host", "localhost"))
KVDB_PORT = int(os.getenv("KVDB_PORT", settings["kv_db"].get("port", "6379")))
KVDB_URI = os.getenv("KVDB_URI", settings["kv_db"].get("uri", None))
KVDB_ENABLED = settings["kv_db"].get("enabled", False)


DATABASES = settings.get("databases", {})


######################
#  MongoDB Settings  #
######################
_mongo_settings = DATABASES.get("mongodb", None)
MONGO_ENABLED = False
if _mongo_settings:
    if "MONGO_ENABLED" in os.environ:
        MONGO_ENABLED = os.environ.get("MONGO_ENABLED").lower() == "true"
    else:
        MONGO_ENABLED = _mongo_settings.get("enabled", False)
    MONGO_URI = os.environ.get("MONGO_URI") or _mongo_settings.get("uri")
    MONGO_HOST = os.environ.get("MONGO_HOST") or _mongo_settings.get("host", "localhost")
    MONGO_PORT = int(os.environ.get("MONGO_PORT") or _mongo_settings.get("port", 27017))
    MONGO_DB = _mongo_settings.get("db", PROJECT_NAME)
    MONGO_CREATE_INDEX = _mongo_settings.get("create_collection_index", True)

######################
#  LMDB Settings  #
######################
LMDB_SETTINGS = DATABASES.get("lmdb", {})
LMDB_ENABLED = False
if LMDB_SETTINGS:
    if "LMDB_ENABLED" in os.environ:
        LMDB_ENABLED = os.environ.get("LMDB_ENABLED").lower() == "true"
    else:
        LMDB_ENABLED = LMDB_SETTINGS.get("enabled", False)

# if not LMDB_ENABLED and not MONGO_ENABLED:
#     # At least one of these variables need to be enabled.
#     LMDB_ENABLED = True

##########################
# DB Buffer Settings        #
##########################
db_buffer_settings = settings["db_buffer"]

INSERTION_BUFFER_TIME = db_buffer_settings.get("insertion_buffer_time_secs", None)  # In seconds:
DB_BUFFER_SIZE = int(db_buffer_settings.get("buffer_size", 50))
REMOVE_EMPTY_FIELDS = db_buffer_settings.get("remove_empty_fields", False)
DB_INSERTER_MAX_TRIALS_STOP = db_buffer_settings.get("stop_max_trials", 240)
DB_INSERTER_SLEEP_TRIALS_STOP = db_buffer_settings.get("stop_trials_sleep", 0.01)


###########################
# PROJECT SYSTEM SETTINGS #
###########################

DB_FLUSH_MODE = settings["project"].get("db_flush_mode", "offline")
# DEBUG_MODE = settings["project"].get("debug", False)
PERF_LOG = settings["project"].get("performance_logging", False)
JSON_SERIALIZER = settings["project"].get("json_serializer", "default")
REPLACE_NON_JSON_SERIALIZABLE = settings["project"].get("replace_non_json_serializable", True)
ENRICH_MESSAGES = settings["project"].get("enrich_messages", True)
DUMP_BUFFER_PATH = settings["project"].get("dump_buffer_path", "flowcept_messages.jsonl")

TELEMETRY_CAPTURE = settings.get("telemetry_capture", None)
TELEMETRY_ENABLED = TELEMETRY_CAPTURE is not None and len(TELEMETRY_CAPTURE)

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
settings.setdefault("web_server", {})
_webserver_settings = settings.get("web_server", {})
WEBSERVER_HOST = _webserver_settings.get("host", "0.0.0.0")
WEBSERVER_PORT = int(_webserver_settings.get("port", 5000))

######################
#    ANALYTICS      #
######################

ANALYTICS = settings.get("analytics", None)

####################
# INSTRUMENTATION  #
####################

INSTRUMENTATION = settings.get("instrumentation", {})
INSTRUMENTATION_ENABLED = INSTRUMENTATION.get("enabled", True)

AGENT = settings.get("agent", {})
AGENT_HOST = os.getenv("AGENT_HOST", settings["agent"].get("mcp_host", "localhost"))
AGENT_PORT = int(os.getenv("AGENT_PORT", settings["agent"].get("mcp_port", "8000")))

####################
# Enabled ADAPTERS #
####################
ADAPTERS = set()

for adapter in settings.get("adapters", set()):
    ADAPTERS.add(settings["adapters"][adapter].get("kind"))
