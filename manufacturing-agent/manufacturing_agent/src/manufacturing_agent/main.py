#!/usr/bin/env python
import sys
import warnings
import os
import json

from manufacturing_agent.crew import ManufacturingAgentCrew

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# Note from Miaosen: This is the main entry point for the CrewAI but not used by our project.
def run():
    """
    Run the crew.
    """
    # Try to get layer number from environment variable first, then prompt user
    layer_number = os.environ.get('LAYER_NUMBER')
    
    if not layer_number:
        layer_number = input("Enter the layer number (default: 1): ").strip()
        if not layer_number:
            layer_number = "1"
    
    print(f"Running manufacturing agent for layer {layer_number}")

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    # The crew requires a JSON payload via either:
    #   • ENV var `CREW_INPUT_JSON`
    #   • First CLI argument (stringified JSON)
    #   • STDIN (piped JSON)
    # If none is supplied we exit with a helpful message.

    raw_json = os.getenv("CREW_INPUT_JSON")
    if not raw_json and len(sys.argv) > 1:
        raw_json = sys.argv[1]
    if not raw_json and not sys.stdin.isatty():
        raw_json = sys.stdin.read()

    if not raw_json:
        raise SystemExit(
            "No input JSON provided. Supply via ENV CREW_INPUT_JSON, CLI arg, or STDIN."
        )

    try:
        inputs = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON input: {exc}")

    try:
        ManufacturingAgentCrew().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise SystemExit(f"An error occurred while running the crew: {e}")