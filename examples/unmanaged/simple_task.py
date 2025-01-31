import argparse


def run_task(workflow_id):
    print(f"Task ran successfully for the workflow_id {workflow_id}.")


def parse_args():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Process a workflow by ID.")
    parser.add_argument("workflow_id", type=str, help="The ID of the workflow to process")

    # Parse arguments
    args = parser.parse_args()
    return args.workflow_id


if __name__ == "__main__":
    workflow_id = parse_args()
    from flowcept import Flowcept, FlowceptTask
    f = Flowcept(workflow_id=workflow_id,
                 bundle_exec_id=workflow_id,
                 start_persistence=False, save_workflow=False)
    f.start()
    t = FlowceptTask(workflow_id=workflow_id, activity_id="test_task")
    run_task(workflow_id)
    t.end()
    f.stop()

