"""
This is a very simple script to show the basic instrumentation capabilities of Flowcept, using its most straightforward
way of capturing workflow provenance from functions and accessing its internal buffer.

This very simple scenario does not need any database or external service.
Flowcept will flush its buffer to a file in the end if a dump_buffer_path is defined in the settings.

For online provenance analysis, HPC requirements, federated/highly distributed execution,
 data observability from existing adapters, PyTorch models, telemetry capture optimization,
 query requirements, or any other provided feature or custom requirements, see the rest of examples/ directory.

This example's intent is to be simple just to show the most basic utilization scenario for Flowcept.

Note:
- Adding output_names is not required, but they will make the generated provenance look nicer (and more semantic).
"""
import json

from flowcept import Flowcept, flowcept_task


@flowcept_task(output_names="o1")
def sum_one(i1):
    return i1+1


@flowcept_task(output_names="o2")
def mult_two(o1):
    return o1*2


def main():
    """
    This contains the workflow code.
    """

    n = 3
    with Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False):
        o1 = sum_one(n)
        o2 = mult_two(o1)
    print("Final output", o2)


if __name__ == "__main__":

    main()

    prov_messages = Flowcept.read_messages_file()
    assert len(prov_messages) == 2
    print(json.dumps(prov_messages, indent=2))


