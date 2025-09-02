"""
This is a very simple script to show the basic instrumentation capabilities of Flowcept, using its most straightforward
way of capturing workflow provenance from functions and accessing its internal buffer.

This very simple scenario does not need any database or external service.

For HPC requirements, federated/highly distributed execution, data observability from existing adapters, PyTorch models,
telemetry capture optimization, query requirements, or any other custom requirements, do not use this example.
Its intent is to be simple just to show the most basic utilization scenario for Flowcept.

Note:
- Adding output_names is not required, but they will make the generated provenance look nicer (and more semantic).
"""
import json

from flowcept import Flowcept, flowcept_task


@flowcept_task(output_names="r")
def sum_one(i1):
    return i1+1


@flowcept_task(output_names="z")
def mult_two(r):
    return r*2


with Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False) as f:
    n = 3
    o1 = sum_one(n)
    o2 = mult_two(o1)
    print(json.dumps(f.buffer, indent=2))
    assert len(f.buffer) == 2
