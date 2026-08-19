"""Observe a Codex session JSONL file with Flowcept.

Setup:
    pip install "flowcept[codex]"
    flowcept --init-settings --codex -y

Then edit your Flowcept settings file:
    adapters.codex.file_path: /path/to/codex/session.jsonl
    adapters.codex.declared_provenance_enabled: false

With ``declared_provenance_enabled: false`` the adapter runs in OPL mode and
captures the provenance it can infer directly from the Codex JSONL log.

For DPL mode, install the bundled agent-loop-provenance skill before starting
the Codex session, then set:
    adapters.codex.declared_provenance_enabled: true

The skill instructions live in:
    resources/skills/agent-loop-provenance/README.md

Run this observer while the Codex session is active, or replay an existing JSONL
by pointing ``adapters.codex.file_path`` to that file.
"""

from time import sleep

from flowcept import Flowcept
from flowcept.configs import settings


if __name__ == "__main__":
    # Configure adapters.codex.file_path in settings.yaml before running this.
    file_path = settings["adapters"]["codex"]["file_path"]
    declared = settings["adapters"]["codex"].get("declared_provenance_enabled", False)
    print(f"Codex JSONL path: {file_path}")
    print(f"Declared provenance enabled: {declared}")

    with Flowcept("codex", save_workflow=False) as flowcept:
        print("Codex adapter running. Press Ctrl+C to stop.")
        try:
            while True:
                sleep(2)
                print(f"records in buffer: {len(flowcept.get_buffer())}")
        except KeyboardInterrupt:
            print("Stopping Codex adapter...")
