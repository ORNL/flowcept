from flowcept import Flowcept, flowcept_task

@flowcept_task
def sum_one(n):
    return n + 1


@flowcept_task
def mult_two(n):
    return n * 2


with Flowcept(workflow_name='test_workflow'):
    n = 3
    o1 = sum_one(n)
    o2 = mult_two(o1)
    print(o2)

print(Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id}))

