import os
import subprocess
import sys
import traceback
from itertools import product

import yaml

from flowcept.configs import SETTINGS_PATH

LOG_FILE = "test_log.log"


def write_log(msg: str):
    with open(LOG_FILE, "a") as log_file:
        print(msg)
        log_file.write(msg+"\n")
        log_file.flush()
        os.fsync(log_file.fileno())


def write_exception(msg: str, exception: Exception):
    print(msg)
    write_log(msg)
    with open(LOG_FILE, "a") as log_file:
        traceback.print_exception(type(exception), exception, exception.__traceback__, file=log_file)
        log_file.flush()
        os.fsync(log_file.fileno())


def run_test(config, max_runs=50):

    update_yaml_file(config)

    for i in range(0, max_runs):
        success = run_process()
        if not success:
            return False
        write_log(f"Done with {i}")

    return True


def one():
    config = {'what': 'parent_and_children', 'children_mode': 'tensor_inspection',
              'epoch_loop': 'default', 'batch_loop': 'default', 'capture_epochs_at_every': 1}
    run_test(max_runs=1, config=config)


def all():
    configs = {
        "what": ["parent_and_children", "parent_only"],
        "children_mode": ["tensor_inspection", "telemetry_and_tensor_inspection"],
        "epoch_loop": ["default", "lightweight"],
        "batch_loop": ["default", "lightweight"],
        "capture_epochs_at_every": [1, 2]
    }

    keys = configs.keys()
    values = configs.values()

    combinations = [dict(zip(keys, combination)) for combination in product(*values)]

    for i, config in enumerate(combinations, start=1):
        write_log(f"\n\nStarting for combination {i}/{len(combinations)}: {config}")

        try:
            success = run_test(max_runs=3, config=config)
            if not success:
                write_log(str(i) + "--> " + str(config))
                sys.exit(1)
        except Exception as e:
            write_exception(f"\n\n!!!!!!##### ERROR for combination {config}\n", e)
            raise Exception(e)


def update_yaml_file(torch_config: dict) -> None:
    with open(SETTINGS_PATH, 'r') as file:
        data = yaml.safe_load(file) or {}  # Load YAML or initialize as empty dict

    # Apply updates
    data["instrumentation"]["torch"] = torch_config

    # Save updated YAML back to file
    with open(SETTINGS_PATH, 'w') as file:
        yaml.safe_dump(data, file, default_flow_style=False)
    print("Updated settings file")


def run_process():
    current_script_path = os.path.abspath(__file__)
    parent_directory = os.path.dirname(current_script_path)
    llm_main_script = os.path.join(parent_directory, "llm_main_example.py")
    command = ["python", llm_main_script]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Print the output line by line in real-time
    for line in process.stdout:
        print(line, end="")  # Print to console

    process.wait()

    if process.returncode != 0:
        print(f"\nScript failed with return code {process.returncode}")
        return False
    else:
        print("\nScript finished successfully!")
        return True


if __name__ == "__main__":
    all()
