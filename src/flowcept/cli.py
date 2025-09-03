"""
Flowcept CLI.

How to add a new command:
--------------------------
1. Write a function with type-annotated arguments and a NumPy-style docstring.
2. Add it to one of the groups in `COMMAND_GROUPS`.
3. It will automatically become available as `flowcept --<function-name>` (underscores become hyphens).

Supports:
- `flowcept --command`
- `flowcept --command --arg=value`
- `flowcept -h` or `flowcept` for full help
- `flowcept --help --command` for command-specific help
"""

import subprocess
from typing import Dict, Optional
import argparse
import os
import sys
import json
import textwrap
import inspect
from functools import wraps
from importlib import resources
from pathlib import Path
from typing import List

from flowcept import Flowcept, configs


def no_docstring(func):
    """Decorator to silence linter for missing docstrings."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def show_settings():
    """
    Show Flowcept configuration.
    """
    config_data = {
        "session_settings_path": configs.SETTINGS_PATH,
        "env_FLOWCEPT_SETTINGS_PATH": os.environ.get("FLOWCEPT_SETTINGS_PATH", None),
    }
    print(f"This is the settings path in this session: {configs.SETTINGS_PATH}")
    print(
        f"This is your FLOWCEPT_SETTINGS_PATH environment variable value: {config_data['env_FLOWCEPT_SETTINGS_PATH']}"
    )


def init_settings():
    """
    Create a new settings.yaml file in your home directory under ~/.flowcept.
    """
    dest_path = Path(os.path.join(configs._SETTINGS_DIR, "settings.yaml"))

    if dest_path.exists():
        overwrite = input(f"{dest_path} already exists. Overwrite? (y/N): ").strip().lower()
        if overwrite != "y":
            print("Operation aborted.")
            return

    os.makedirs(configs._SETTINGS_DIR, exist_ok=True)

    SAMPLE_SETTINGS_PATH = str(resources.files("resources").joinpath("sample_settings.yaml"))

    with open(SAMPLE_SETTINGS_PATH, "rb") as src_file, open(dest_path, "wb") as dst_file:
        dst_file.write(src_file.read())
    print(f"Copied {configs.SETTINGS_PATH} to {dest_path}")


def version():
    """
    Returns this Flowcept's installation version.
    """
    from flowcept.version import __version__
    print(f"Flowcept {__version__}")


def start_consumption_services(bundle_exec_id: str = None, check_safe_stops: bool = False, consumers: List[str] = None):
    """
    Start services that consume data from a queue or other source.

    Parameters
    ----------
    bundle_exec_id : str, optional
        The ID of the bundle execution to associate with the consumers.
    check_safe_stops : bool, optional
        Whether to check for safe stopping conditions before starting.
    consumers : list of str, optional
        List of consumer IDs to start. If not provided, all consumers will be started.
    """
    print("Starting consumption services...")
    print(f"  bundle_exec_id: {bundle_exec_id}")
    print(f"  check_safe_stops: {check_safe_stops}")
    print(f"  consumers: {consumers or []}")

    Flowcept.start_consumption_services(
        bundle_exec_id=bundle_exec_id,
        check_safe_stops=check_safe_stops,
        consumers=consumers,
    )


def stop_consumption_services():
    """
    Stop the document inserter.
    """
    print("Not implemented yet.")


def start_services(with_mongo: bool = False):
    """
    Start Flowcept services (optionally including MongoDB).

    Parameters
    ----------
    with_mongo : bool, optional
        Whether to also start MongoDB.
    """
    print(f"Starting services{' with Mongo' if with_mongo else ''}")
    print("Not implemented yet.")


def stop_services():
    """
    Stop Flowcept services.
    """
    print("Not implemented yet.")


def workflow_count(workflow_id: str):
    """
    Count number of documents in the DB.

    Parameters
    ----------
    workflow_id : str
        The ID of the workflow to count tasks for.
    """
    result = {
        "workflow_id": workflow_id,
        "tasks": len(Flowcept.db.query({"workflow_id": workflow_id})),
        "workflows": len(Flowcept.db.query({"workflow_id": workflow_id}, collection="workflows")),
        "objects": len(Flowcept.db.query({"workflow_id": workflow_id}, collection="objects")),
    }
    print(json.dumps(result, indent=2))


def query(filter: str, project: str = None, sort: str = None, limit: int = 0):
    """
    Query the MongoDB task collection with an optional projection, sort, and limit.

    Parameters
    ----------
    filter : str
        A JSON string representing the MongoDB filter query.
    project : str, optional
        A JSON string specifying fields to include or exclude in the result (MongoDB projection).
    sort : str, optional
        A JSON string specifying sorting criteria (e.g., '[["started_at", -1]]').
    limit : int, optional
        Maximum number of documents to return. Default is 0 (no limit).

    Returns
    -------
    List[dict]
        A list of task documents matching the query.
    """
    _filter, _project, _sort = None, None, None
    if filter:
        _filter = json.loads(filter)
    if project:
        _project = json.loads(project)
    if sort:
        _sort = list(sort)
    print(
        json.dumps(Flowcept.db.query(filter=_filter, projection=_project, sort=_sort, limit=limit), indent=2, default=str)
    )


def get_task(task_id: str):
    """
    Query the Document DB to retrieve a task.

    Parameters
    ----------
    task_id : str
        The identifier of the task.
    """
    _query = {"task_id": task_id}
    print(json.dumps(Flowcept.db.query(_query), indent=2, default=str))


def start_agent(): # TODO: start with gui
    """Start Flowcept agent."""
    from flowcept.agents.flowcept_agent import main

    main()


def start_agent_gui(port: int = None):
    """Start Flowcept agent GUI service.

    Parameters
    ----------
    port : int, optional
        The default port is 8501. Use --port if you want to run the GUI on a different port.
    """

    gui_path = Path(__file__).parent / "agents" / "gui" / "agent_gui.py"
    gui_path = gui_path.resolve()
    cmd = f"streamlit run {gui_path}"

    if port is not None and isinstance(port, int):
        cmd += f" --server.port {port}"

    _run_command(cmd, check_output=True)


def agent_client(tool_name: str, kwargs: str = None):
    """Agent Client.

    Parameters.
    ----------
    tool_name : str
        Name of the tool
    kwargs : str, optional
        A stringfied JSON containing the kwargs for the tool, if needed.
    """
    print(f"Going to run agent tool '{tool_name}'.")
    if kwargs:
        try:
            kwargs = json.loads(kwargs)
            print(f"Using kwargs: {kwargs}")
        except Exception as e:
            print(f"Could not parse kwargs as a valid JSON: {kwargs}")
            print(e)
    print("-----------------")
    from flowcept.agents.agent_client import run_tool

    result = run_tool(tool_name, kwargs)[0]

    print(result)


def check_services():
    """
    Run a full diagnostic test on the Flowcept system and its dependencies.

    This function:
    - Prints the current configuration path.
    - Checks if required services (e.g., MongoDB, agent) are alive.
    - Runs a test function wrapped with Flowcept instrumentation.
    - Verifies MongoDB insertion (if enabled).
    - Verifies agent communication and LLM connectivity (if enabled).

    Returns
    -------
    None
        Prints diagnostics to stdout; returns nothing.
    """
    print(f"Testing with settings at: {configs.SETTINGS_PATH}")
    from flowcept.configs import MONGO_ENABLED, AGENT, KVDB_ENABLED

    if not Flowcept.services_alive():
        print("Some of the enabled services are not alive!")
        return

    check_safe_stops = KVDB_ENABLED

    from uuid import uuid4
    from flowcept.instrumentation.flowcept_task import flowcept_task

    workflow_id = str(uuid4())

    @flowcept_task
    def test_function(n: int) -> Dict[str, int]:
        return {"output": n + 1}

    with Flowcept(workflow_id=workflow_id, check_safe_stops=check_safe_stops):
        test_function(2)

    if MONGO_ENABLED:
        print("MongoDB is enabled, so we are testing it too.")
        tasks = Flowcept.db.query({"workflow_id": workflow_id})
        if len(tasks) != 1:
            print(f"The query result, {len(tasks)}, is not what we expected.")
            return

    if AGENT.get("enabled", False):
        print("Agent is enabled, so we are testing it too.")
        from flowcept.agents.agent_client import run_tool

        try:
            print(run_tool("check_liveness"))
        except Exception as e:
            print(e)
            return

        print("Testing LLM connectivity")
        check_llm_result = run_tool("check_llm")[0]
        print(check_llm_result)

        if "error" in check_llm_result.lower():
            print("There is an error with the LLM communication.")
            return
        # TODO: the following needs to be fixed
        # elif MONGO_ENABLED:
        #
        #     print("Testing if llm chat was stored in MongoDB.")
        #     response_metadata = json.loads(check_llm_result.split("\n")[0])
        #     print(response_metadata)
        #     sleep(INSERTION_BUFFER_TIME * 1.05)
        #     chats = Flowcept.db.query({"workflow_id": response_metadata["agent_id"]})
        #     if chats:
        #         print(chats)
        #     else:
        #         print("Could not find chat history. Make sure that the DB Inserter service is on.")
    print("\n\nAll expected services seem to be working properly!")
    return


def stream_messages(print_messages: bool = False, messages_file_path: Optional[str] = None):
    """
    Listen to Flowcept's message stream and optionally echo/save messages.

    Parameters
    ----------
    print_messages : bool, optional
        If True, print each decoded message to stdout.
    messages_file_path : str, optional
        If provided, append each message as JSON (one per line) to this file.
        If the file already exists, a new timestamped file is created instead.
    """
    # Local imports to avoid changing module-level deps
    from flowcept.configs import MQ_TYPE
    if MQ_TYPE != "redis":
        print("This is currently only available for Redis. Other MQ impls coming soon.")
        return

    import os
    import json
    from datetime import datetime
    import redis
    import msgpack
    from flowcept.configs import MQ_HOST, MQ_PORT, MQ_CHANNEL, KVDB_URI
    from flowcept.commons.daos.mq_dao.mq_dao_redis import MQDaoRedis

    def _timestamped_path_if_exists(path: Optional[str]) -> Optional[str]:
        if not path:
            return path
        if os.path.exists(path):
            base, ext = os.path.splitext(path)
            ts = datetime.now().strftime("%Y-%m-%d %H.%M.%S")
            return f"{base} ({ts}){ext}"
        return path

    def _json_dumps(obj) -> str:
        """JSON-dump a msgpack-decoded object; handle bytes safely."""
        def _default(o):
            if isinstance(o, (bytes, bytearray)):
                try:
                    return o.decode("utf-8")
                except Exception:
                    return o.hex()
            raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=_default)

    # Prepare output file (JSONL)
    out_fh = None
    if messages_file_path:
        out_path = _timestamped_path_if_exists(messages_file_path)
        out_fh = open(out_path, "w", encoding="utf-8", buffering=1)  # line-buffered

    # Connect & subscribe
    redis_client = redis.from_url(KVDB_URI) if KVDB_URI else redis.Redis(host=MQ_HOST, port=MQ_PORT, db=0)
    pubsub = redis_client.pubsub()
    pubsub.subscribe(MQ_CHANNEL)

    print(f"Listening for messages on channel '{MQ_CHANNEL}'... (Ctrl+C to exit)")

    try:
        for message in pubsub.listen():
            if not message or message.get("type") in MQDaoRedis.MESSAGE_TYPES_IGNORE:
                continue

            data = message.get("data")
            if not isinstance(data, (bytes, bytearray)):
                print(f"Skipping message with unexpected data type: {type(data)} - {data}")
                continue

            try:
                msg_obj = msgpack.loads(data, strict_map_key=False)
                msg_type = msg_obj.get("type", None)
                print(f"\nReceived a message! type={msg_type}")

                if print_messages:
                    print(_json_dumps(msg_obj))

                if out_fh is not None:
                    out_fh.write(_json_dumps(msg_obj))
                    out_fh.write("\n")

            except Exception as e:
                print(f"Error decoding message: {e}")

    except KeyboardInterrupt:
        print("\nInterrupted, shutting down...")
    finally:
        try:
            if out_fh:
                out_fh.close()
            pubsub.close()
        except Exception:
            pass


COMMAND_GROUPS = [
    ("Basic Commands", [version, check_services, show_settings, init_settings, start_services, stop_services]),
    ("Consumption Commands", [start_consumption_services, stop_consumption_services, stream_messages]),
    ("Database Commands", [workflow_count, query, get_task]),
    ("Agent Commands", [start_agent, agent_client, start_agent_gui]),
]

COMMANDS = set(f for _, fs in COMMAND_GROUPS for f in fs)


def _run_command(cmd_str: str, check_output: bool = True, popen_kwargs: Optional[Dict] = None) -> Optional[str]:
    """
    Run a shell command with optional output capture.

    Parameters
    ----------
    cmd_str : str
        The command to execute.
    check_output : bool, optional
        If True, capture and return the command's standard output.
        If False, run interactively (stdout/stderr goes to terminal).
    popen_kwargs : dict, optional
        Extra keyword arguments to pass to subprocess.run.

    Returns
    -------
    output : str or None
        The standard output of the command if check_output is True, else None.

    Raises
    ------
    subprocess.CalledProcessError
        If the command exits with a non-zero status.
    """
    if popen_kwargs is None:
        popen_kwargs = {}

    kwargs = {"shell": True, "check": True, **popen_kwargs}

    if check_output:
        kwargs.update({"capture_output": True, "text": True})
        result = subprocess.run(cmd_str, **kwargs)
        return result.stdout.strip()
    else:
        subprocess.run(cmd_str, **kwargs)
        return None


def _parse_numpy_doc(docstring: str):
    parsed = {}
    lines = docstring.splitlines() if docstring else []
    in_params = False
    for line in lines:
        line = line.strip()
        if line.lower().startswith("parameters"):
            in_params = True
            continue
        if in_params:
            if " : " in line:
                name, typeinfo = line.split(" : ", 1)
                parsed[name.strip()] = {"type": typeinfo.strip(), "desc": ""}
            elif parsed:
                last = list(parsed)[-1]
                parsed[last]["desc"] += " " + line
    return parsed


@no_docstring
def main():  # noqa: D103
    parser = argparse.ArgumentParser(
        description="Flowcept CLI", formatter_class=argparse.RawTextHelpFormatter, add_help=False
    )

    for func in COMMANDS:
        doc = func.__doc__ or ""
        func_name = func.__name__
        flag = f"--{func_name.replace('_', '-')}"
        short_help = doc.strip().splitlines()[0] if doc else ""
        parser.add_argument(flag, action="store_true", help=short_help)

        for pname, param in inspect.signature(func).parameters.items():
            arg_name = f"--{pname.replace('_', '-')}"
            params_doc = _parse_numpy_doc(doc).get(pname, {})
            help_text = f"{params_doc.get('type', '')} - {params_doc.get('desc', '').strip()}"
            if param.annotation == bool:
                parser.add_argument(arg_name, action="store_true", help=help_text)
            elif param.annotation == List[str]:
                parser.add_argument(arg_name, type=lambda s: s.split(","), help=help_text)
            else:
                parser.add_argument(arg_name, type=str, help=help_text)

    # Handle --help --command
    help_flag = "--help" in sys.argv or "-h" in sys.argv
    command_flags = {f"--{f.__name__.replace('_', '-')}" for f in COMMANDS}
    matched_command_flag = next((arg for arg in sys.argv if arg in command_flags), None)

    if help_flag and matched_command_flag:
        command_func = next(f for f in COMMANDS if f"--{f.__name__.replace('_', '-')}" == matched_command_flag)
        doc = command_func.__doc__ or ""
        sig = inspect.signature(command_func)
        print(f"\nHelp for `flowcept {matched_command_flag}`:\n")
        print(textwrap.indent(doc.strip(), "  "))
        print("\n  Arguments:")
        params = _parse_numpy_doc(doc)
        for pname, p in sig.parameters.items():
            meta = params.get(pname, {})
            opt = p.default != inspect.Parameter.empty
            print(
                f"    --{pname.replace('_', '-'):<18} {meta.get('type', 'str')}, "
                f"{'optional' if opt else 'required'} - {meta.get('desc', '').strip()}"
            )
        print()
        sys.exit(0)

    if len(sys.argv) == 1 or help_flag:
        print("\nFlowcept CLI\n")
        for group, funcs in COMMAND_GROUPS:
            print(f"{group}:\n")
            for func in funcs:
                name = func.__name__
                flag = f"--{name.replace('_', '-')}"
                doc = func.__doc__ or ""
                summary = doc.strip().splitlines()[0] if doc else ""
                sig = inspect.signature(func)
                print(f"  flowcept {flag}", end="")
                for pname, p in sig.parameters.items():
                    is_opt = p.default != inspect.Parameter.empty
                    print(f" [--{pname.replace('_', '-')}] " if is_opt else f" --{pname.replace('_', '-')}", end="")
                print(f"\n      {summary}")
                params = _parse_numpy_doc(doc)
                if params:
                    print("      Arguments:")
                    for argname, meta in params.items():
                        opt = sig.parameters[argname].default != inspect.Parameter.empty
                        print(
                            f"          --"
                            f"{argname.replace('_', '-'):<18} {meta['type']}, "
                            f"{'optional' if opt else 'required'} - {meta['desc'].strip()}"
                        )
                print()
        print("Run `flowcept --<command>` to invoke a command.\n")
        sys.exit(0)

    args = vars(parser.parse_args())

    for func in COMMANDS:
        flag = f"--{func.__name__.replace('_', '-')}"
        if args.get(func.__name__.replace('-', '_')):
            sig = inspect.signature(func)
            kwargs = {}
            for pname in sig.parameters:
                val = args.get(pname.replace('-', '_'))
                if val is not None:
                    kwargs[pname] = val
            func(**kwargs)
            break
    else:
        print("Unknown command. Use `flowcept -h` to see available commands.")
        sys.exit(1)


if __name__ == "__main__":
    main()
    #check_services()
