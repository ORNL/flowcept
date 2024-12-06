"""Command line interface (CLI) module."""

import argparse
import shutil
import importlib.metadata
import importlib.resources
from pathlib import Path


def create_config(args: argparse.Namespace):
    """Create configuration file."""
    settings_yaml = importlib.resources.files("flowcept") / "settings/sample_settings.yaml"

    if args.path:
        Path(args.path).mkdir(parents=True, exist_ok=True)
        shutil.copy(f"{settings_yaml}", f"{args.path}")
        print(f"Created `sample_settings.yaml` in {args.path} directory.")
    else:
        shutil.copy(f"{settings_yaml}", ".")
        print("Created `sample_settings.yaml` in current directory.")


def main():
    """Run command line parsers."""
    # Create main parser and subparsers
    parser = argparse.ArgumentParser(description="FlowCept CLI")
    parser.add_argument(
        "--version", "-v", action="version", version=importlib.metadata.version("flowcept")
    )

    subparsers = parser.add_subparsers(title="subcommands", help="valid subcommands")

    # Create subparser for `config` subcommand
    config_parser = subparsers.add_parser("config", help="configuration command")
    config_parser.set_defaults(func=create_config)
    config_parser.add_argument("--path", help="config file directory")

    args = parser.parse_args()

    # Run the function associated with a subcommand
    if hasattr(args, "func"):
        args.func(args)
