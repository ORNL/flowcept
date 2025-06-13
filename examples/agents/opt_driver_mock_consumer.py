import json
from time import sleep
import random
from typing import Dict, List

from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.consumers.agent.client_agent import run_tool
from flowcept.flowceptor.consumers.base_consumer import BaseConsumer
from flowcept.instrumentation.flowcept_task import flowcept_task

try:
    print(run_tool("check_liveness"))
except Exception as e:
    print(e)
    pass


class AdamantineDriver(BaseConsumer):

    @flowcept_task(tags=["run_tool"])
    @staticmethod
    def generate_options_set(layer, planned_controls, number_of_options):
        return

    @flowcept_task(tags=["run_tool"])
    @staticmethod
    def choose_option(l2_error, planned_controls):
        return

    def __init__(self, number_of_options, max_layers, planned_controls: List[Dict], first_layer_ix: int = 2):
        super().__init__()
        self._layers_count = first_layer_ix
        self._number_of_options = number_of_options
        self._max_layers = max_layers
        self._planned_controls = planned_controls
        self._current_controls_options = None

        AdamantineDriver.generate_options_set(
            layer=self._layers_count,
            planned_controls=self._planned_controls,
            number_of_options=self._number_of_options
        )

    def message_handler(self, msg_obj: Dict) -> bool:
        """
        Pseudocode for this function:

        MAX_LAYERS = 5
        current_layer = 2

        call Agent tool "generate_options_set" for current_layer

        on message received:

            if message is not a tool result:
                continue

            if tool_name == "generate_options_set":
                get control options
                run a simulation for the current layer given these options
                call Agent tool "choose_option" with simulation result

            elif tool_name == "choose_option":
                print chosen option and reason

                current_layer+=1

                if current_layer == MAX_LAYERS:
                    print completion message
                    return False  # stop listening loop

                else:
                    call Agent tool "generate_options_set" for current_layer

            return True  # keep listening

        """
        if msg_obj.get('type', '') == 'task':
            if msg_obj.get("tags", [''])[0] == 'tool_result':
                tool_name = msg_obj.get("activity_id")
                if tool_name == "generate_options_set":
                    tool_output = msg_obj.get("generated")
                    self._current_controls_options = tool_output.get("control_options")
                    l2_error = simulate_layer(layer_number=self._layers_count, control_options=self._current_controls_options)
                    AdamantineDriver.choose_option(
                        l2_error=l2_error,
                        planned_controls=self._planned_controls,
                    )

                elif tool_name == "choose_option":
                    tool_output = msg_obj.get("generated")
                    option = tool_output.get("option")
                    reason = tool_output.get("reason")
                    print(f"Agent chose option {option}: {self._current_controls_options[option]}. Reason: {reason}")

                    self._layers_count += 1

                    if self._layers_count == self._max_layers:
                        print("All layers have been processed!")
                        return False

                    AdamantineDriver.generate_options_set(
                        layer=self._layers_count,
                        planned_controls=self._planned_controls,
                        number_of_options=self._number_of_options
                    )
            if msg_obj.get("subtype", '') == "llm_query":
                print("Msg from agent.")

        else:
            print(f"We got a msg with different type: {msg_obj.get("type", None)}")
        return True


def generate_mock_planned_control(config, number_of_options):
    def _generate_control_options():
        dwell_arr = list(range(10, 121, 5))
        control_options = []
        for k in range(number_of_options):
            control_options.append({
                "power": random.randint(0, 350),
                "dwell_0": dwell_arr[random.randint(0, len(dwell_arr) - 1)],
                "dwell_1": dwell_arr[random.randint(0, len(dwell_arr) - 1)],
            })
        return control_options

    planned_controls = []
    for i in range(config["max_layers"]):
        possible_options = _generate_control_options()
        planned_controls.append(possible_options[random.randint(0, len(possible_options) - 1)])
    print(json.dumps(planned_controls, indent=2))
    return planned_controls


@flowcept_task
def simulate_layer(layer_number: int, control_options: List[Dict]):

    def forward_simulation(_control_option: Dict) -> float:
        """Calculate a score (n2 norm) for a given control_option"""
        assert len(_control_option) == 3
        sleep(0.1)
        return random.randint(0, 100)

    print(f"Simulating for layer {layer_number}")
    print(f"These are the input control options (generated by the agent): {control_options}")
    l2_error = []
    for control_option in control_options:
        l2_error.append(forward_simulation(control_option))

    print(f"These are the scores calculated by this simulation for these options: {l2_error}")
    return l2_error


def main():
    config = {"max_layers": 3, "number_of_options": 1}

    fc = Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False, workflow_args=config)
    fc.start()

    number_of_options = config["number_of_options"]
    planned_controls = generate_mock_planned_control(config, number_of_options)

    driver = AdamantineDriver(
        number_of_options=config["number_of_options"],
        max_layers=config["max_layers"],
        planned_controls=planned_controls,
        first_layer_ix=2
    )
    driver.start(threaded=False)
    fc.stop()


if __name__ == "__main__":
    main()
