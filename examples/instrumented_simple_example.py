from flowcept import Flowcept, flowcept_task


@flowcept_task
def sum_one(n):
    return n + 1


@flowcept_task
def mult_two(n):
    return n * 2


with Flowcept():
    n = 3
    o1 = sum_one(n)
    o2 = mult_two(o1)
    print(o2)
docs = Flowcept.db.get_tasks_from_current_workflow()
print(len(docs))
assert len(docs) == 2

