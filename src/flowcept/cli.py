import argparse
import os
import sys
from typing import List

from flowcept import Flowcept

from flowcept import configs

def show_config():
    """Show Flowcept configuration."""
    print(f"This is the settings path in this session: {configs.SETTINGS_PATH}.")
    print(f"This is your FLOWCEPT_SETTINGS_PATH environment variable value: {os.environ.get('FLOWCEPT_SETTINGS_PATH', None)}")


def start_consumption_services(bundle_exec_id: str = None, check_safe_stops: bool = False, consumers: List[str] = None):
    """Start services that consume data from a queue or other source."""
    print("Starting consumption services...")
    print(f"  bundle_exec_id: {bundle_exec_id}")
    print(f"  check_safe_stops: {check_safe_stops}")
    print(f"  consumers: {consumers or []}")

    Flowcept.start_consumption_services(bundle_exec_id=bundle_exec_id, check_safe_stops=check_safe_stops,
                                        consumers=consumers)


def start_services(with_mongo=False):
    """Start Flowcept services (optionally including MongoDB)."""
    print(f"Starting services{' with Mongo' if with_mongo else ''}")
    print("Not implemented yet.")


def stop_services():
    """Stop Flowcept services."""
    print("Not implemented yet.")


def stop_consumption_services():
    """Stop the document inserter."""
    print("Not implemented yet.")


def main():
    parser = argparse.ArgumentParser(description="Flowcept CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Helper to simplify adding commands
    def add_cmd(func, args_spec=[]):
        cmd_name = func.__name__.replace("_", "-")

        # Generate a short summary of the args to show in `flowcept -h`
        args_summary = " ".join(
            f"{'/'.join(flag for flag in spec['flags'])}"
            if spec["kwargs"].get("action") != "store_true"
            else f"[{spec['flags'][-1]}]"
            for spec in args_spec
        )

        doc = func.__doc__ or ""
        help_str = f"{doc.strip()}  Args: {args_summary}" if args_summary else doc

        cmd_parser = subparsers.add_parser(cmd_name, help=help_str)
        for arg_spec in args_spec:
            cmd_parser.add_argument(*arg_spec["flags"], **arg_spec["kwargs"])
        cmd_parser.set_defaults(_func=func)

    # Define commands
    add_cmd(show_config)
    add_cmd(start_services, [
        {"flags": ["with_mongo"], "kwargs": {"nargs": "?", "default": None, "help": "Include 'with-mongo' to also start MongoDB"}}
    ])
    add_cmd(stop_services)
    add_cmd(stop_consumption_services)
    add_cmd(start_consumption_services, [
        {"flags": ["--bundle-exec-id"], "kwargs": {"type": str, "default": None, "help": "Bundle execution ID"}},
        {"flags": ["--check-safe-stops"], "kwargs": {"action": "store_true", "help": "Enable safe stop check"}},
        {"flags": ["--consumers"], "kwargs": {
            "type": lambda s: s.split(","), "default": None, "help": "Comma-separated list of consumers"
        }},
    ])

    args = parser.parse_args()

    if hasattr(args, "_func"):
        kwargs = vars(args).copy()
        del kwargs["command"]
        del kwargs["_func"]
        args._func(**kwargs)
    else:
        parser.print_help()
        sys.exit(1)

