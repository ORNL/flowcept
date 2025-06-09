from time import sleep
import random
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.consumers.agent.client_agent import run_tool
from flowcept.instrumentation.flowcept_task import flowcept_task


@flowcept_task
def simulate_layer(layer_number: int):
    power_arr = [100, 150, 200, 250, 300, 350]
    dwell_arr = [30, 60]

    control_options = [
        f"{power_arr[random.randint(0, len(power_arr)-1)]}W power reheat pass, {power_arr[random.randint(0, len(power_arr)-1)]}s dwell",
        f"{dwell_arr[random.randint(0, len(dwell_arr)-1)]}s dwell, {dwell_arr[random.randint(0, len(dwell_arr)-1)]}s dwell",
        f"{dwell_arr[random.randint(0, len(dwell_arr)-1)]}s dwell, {power_arr[random.randint(0, len(power_arr)-1)]}W power reheat pass",
        f"{power_arr[random.randint(0, len(power_arr)-1)]}W power reheat pass, {power_arr[random.randint(0, len(power_arr)-1)]}W power reheat pass"
    ]
    l2_error = [
        random.randint(100, 350),
        random.randint(100, 500),
        random.randint(100, 500),
        random.randint(100, 600)
    ]
    sleep(5/(layer_number+1))
    return {"control_options": control_options, "l2_error": l2_error}


try:
    print(run_tool("check_liveness"))
except Exception as e:
    print(e)
    pass


def adaptive_control_workflow(config):
    for i in range(config["max_layers"]):
        print()
        print(f"Starting simulation for Layer {i}; ", end='')
        simulation_output = simulate_layer(layer_number=i)
        print(simulation_output)


if __name__ == "__main__":
    with Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False):
        config = {"max_layers": 5}
        adaptive_control_workflow(config)


