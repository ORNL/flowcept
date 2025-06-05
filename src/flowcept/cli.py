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

import argparse
import os
import sys
import json
import textwrap
import inspect
from functools import wraps
from typing import List

from flowcept import Flowcept, configs


def no_docstring(func):
    """Decorator to silence linter for missing docstrings."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def show_config():
    """
    Show Flowcept configuration.
    """
    config_data = {
        "session_settings_path": configs.SETTINGS_PATH,
        "env_FLOWCEPT_SETTINGS_PATH": os.environ.get("FLOWCEPT_SETTINGS_PATH", None),
    }
    print(f"This is the settings path in this session: {configs.SETTINGS_PATH}")
    print(
        f"This is your FLOWCEPT_SETTINGS_PATH environment variable value: "
        f"{config_data['env_FLOWCEPT_SETTINGS_PATH']}"
    )


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


def query(query_str: str):
    """
    Query the Document DB.

    Parameters
    ----------
    query_str : str
        A JSON string representing the Mongo query.
    """
    query = json.loads(query_str)
    print(Flowcept.db.query(query))


COMMAND_GROUPS = [
    ("Basic Commands", [show_config, start_services, stop_services]),
    ("Consumption Commands", [start_consumption_services, stop_consumption_services]),
    ("Database Commands", [workflow_count, query]),
]

COMMANDS = set(f for _, fs in COMMAND_GROUPS for f in fs)


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
            if isinstance(param.annotation, bool):
                parser.add_argument(arg_name, action="store_true", help=help_text)
            elif param.annotation == List[str]:
                parser.add_argument(arg_name, type=lambda s: s.split(","), help=help_text)
            else:
                parser.add_argument(arg_name, type=str, help=help_text)

    # Handle --help --command
    help_flag = "--help" in sys.argv
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
                f"    --{pname:<18} {meta.get('type', 'str')}, "
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
                            f"{argname:<18} {meta['type']}, "
                            f"{'optional' if opt else 'required'} - {meta['desc'].strip()}"
                        )
                print()
        print("Run `flowcept --<command>` to invoke a command.\n")
        sys.exit(0)

    args = vars(parser.parse_args())

    for func in COMMANDS:
        flag = f"--{func.__name__.replace('_', '-')}"
        if args.get(func.__name__.replace("-", "_")):
            sig = inspect.signature(func)
            kwargs = {}
            for pname in sig.parameters:
                val = args.get(pname.replace("-", "_"))
                if val is not None:
                    kwargs[pname] = val
            func(**kwargs)
            break
    else:
        print("Unknown command. Use `flowcept -h` to see available commands.")
        sys.exit(1)


if __name__ == "__main__":
    main()
