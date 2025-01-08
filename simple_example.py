from flowcept import Flowcept, flowcept_task


@flowcept_task
def sum_one(n):
    return n + 1


@flowcept_task
def mult_two(n):
    return n * 2

print("AAA0", flush=True)
flowcept = Flowcept(start_persistence=False).start() # persistence = False means no consumer
print("AAA1", flush=True)
n = 3
o1 = sum_one(n)
print("AAA2", flush=True)
o2 = mult_two(o1)
print("AAA3", flush=True)
print(o2)
print("AAA4", flush=True)
flowcept.stop()
