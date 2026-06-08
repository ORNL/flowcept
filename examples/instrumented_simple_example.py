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
# docs = Flowcept.db.get_tasks_from_current_workflow()
# print(len(docs))
# print(f"Workflow_id={Flowcept.current_workflow_id}")
# assert len(docs) == 2

provenance_card_path = "PROVENANCE_CARD.md"
prov_buffer = Flowcept.read_buffer_file()
report_stats = Flowcept.generate_report(
    records=prov_buffer,
    output_path=provenance_card_path,
)
print(f"{provenance_card_path} generated!")

