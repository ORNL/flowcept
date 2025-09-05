import json
from time import sleep
import random
from typing import Dict, List

from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.agents.agent_client import run_tool
from flowcept.flowceptor.consumers.base_consumer import BaseConsumer
from flowcept.instrumentation.flowcept_task import flowcept_task
from flowcept.instrumentation.task_capture import FlowceptTask

try:
    print(run_tool("check_liveness"))
except Exception as e:
    print(e)
    pass


class AdamantineDriver(BaseConsumer):

    def __init__(self, number_of_options, max_layers, planned_controls: List[Dict], first_layer_ix: int = 2):
        super().__init__()
        self._layers_count = first_layer_ix
        self._number_of_options = number_of_options
        self._max_layers = max_layers
        self._planned_controls = planned_controls
        self._current_controls_options = None

        FlowceptTask(
            subtype="call_agent_task",
            activity_id="generate_options_set",
            used=dict(
                layer=self._layers_count,
                planned_controls=self._planned_controls,
                number_of_options=self._number_of_options
            )
        ).send()

    def message_handler(self, msg_obj: Dict) -> bool:
        """
        Pseudocode for this function:

        inputs:
            MAX_LAYERS = 5
            current_layer = 2
            PLANNED_CONTROL = provided by a previous step

        should_wait_for_incoming_messages = True
        send "Agent Action" message: generate_options_set(current_layer, PLANNED_CONTROL)

        while should_wait_for_incoming_messages:
            message = receive_next_message()

            if message is not "Agent Action Result":
                skip this message

            if action_name == "generate_options_set":
                control_options = message['control_options']
                option_scores = run_simulation(current_layer, control_options)
                send "Agent Action" message: choose_option(option_scores)

            elif action_name == "choose_option":
                chosen_option, reason = message["chosen_option"], message["reason"]
                print(chosen_option, reason)

                current_layer += 1

                if current_layer == MAX_LAYERS:
                    print("All layers have been processed")
                    should_wait_for_incoming_messages = False
                else:
                    send "Agent Action" message: generate_options_set(current_layer, PLANNED_CONTROL)

        """
        msg_type = msg_obj.get('type', '')
        if msg_type == 'task':
            subtype = msg_obj.get("subtype", '')
            if subtype == 'agent_task':
                tool_name = msg_obj.get("activity_id")
                if tool_name == "generate_options_set":
                    tool_output = msg_obj.get("generated")
                    self._current_controls_options = tool_output.get("control_options")
                    l2_error = simulate_layer(layer_number=self._layers_count, control_options=self._current_controls_options)
                    scores = {
                        "layer": self._layers_count,
                        "control_options": self._current_controls_options,
                        "scores": l2_error,
                    }
                    FlowceptTask(
                        subtype="call_agent_task",
                        activity_id="choose_option",
                        used=dict(
                            scores=scores,
                            planned_controls=self._planned_controls,
                        )
                    ).send()

                elif tool_name == "choose_option":
                    tool_output = msg_obj.get("generated")
                    if tool_output is None:
                        self.logger.error(f"An unexpected error happened!: Tool output is None. Msg was: {msg_obj}")
                        if msg_obj.get("stderr", None):
                            self.logger.error(f"This was the error from the agent tool: {msg_obj.get("stderr")}")
                        return False
                    option = tool_output.get("option")
                    explanation = tool_output.get("explanation")
                    label = tool_output.get("label", None)
                    attention = "Attention!!!" if tool_output.get("attention", False) else ""
                    print(f"Agent chose option {option}: {self._current_controls_options[option]}. Explanation: {explanation}. {label}. {attention}")

                    self._layers_count += 1

                    if self._layers_count == self._max_layers:
                        print("All layers have been processed!")
                        return False

                    FlowceptTask(
                        subtype="call_agent_task",
                        activity_id="generate_options_set",
                        used=dict(
                            layer=self._layers_count,
                            planned_controls=self._planned_controls,
                            number_of_options=self._number_of_options
                        )
                    ).send()
        elif msg_type == 'workflow':
            print("Got workflow msg")
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
    config = {"max_layers": 6, "number_of_options": 2, "first_layer_ix": 2}

    fc = Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False, workflow_args=config)
    fc.start()
    print("Campaign_id="+Flowcept.campaign_id)

    number_of_options = config["number_of_options"]
    planned_controls = generate_mock_planned_control(config, number_of_options)

    driver = AdamantineDriver(
        number_of_options=config["number_of_options"],
        max_layers=config["max_layers"],
        planned_controls=planned_controls,
        first_layer_ix=config["first_layer_ix"]
    )
    driver.start(threaded=False)
    fc.stop()


if __name__ == "__main__":
    main()
