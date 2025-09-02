"""
This is a very simple script to show the basic instrumentation capabilities of Flowcept, using its most straightforward
way of capturing workflow provenance from functions and accessing its internal buffer.

This very simple scenario does not need any database or external service.
"""
from flowcept import Flowcept, flowcept_task


@flowcept_task
def sum_one(i1):
    return i1+1


@flowcept_task
def mult_two(i2):
    return i2*2


with Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False) as f:
    n = 3
    o1 = sum_one(i1=n)
    o2 = mult_two(i2=o1)
    print(f.buffer)
    assert len(f.buffer) == 2
