# The code in example file is based on:
# https://blog.paperspace.com/build-a-language-model-using-pytorch/
import itertools
import os
import sys
import uuid

import pandas as pd
import torch
from distributed import LocalCluster, Client

from examples.llm_complex.llm_dataprep import dataprep_workflow
from examples.llm_complex.llm_model import model_train, TransformerModel

from flowcept.configs import MONGO_ENABLED, INSTRUMENTATION
from flowcept import Flowcept
from flowcept.flowceptor.adapters.dask.dask_plugins import FlowceptDaskSchedulerAdapter, \
    FlowceptDaskWorkerAdapter, register_dask_workflow


TORCH_CAPTURE = INSTRUMENTATION.get("torch").get("what")


def _interpolate_values(start, end, step):
    return [start + i * step for i in range((end - start) // step + 1)]


def generate_configs(params):
    param_names = list(params.keys())
    param_values = []

    for param_name in param_names:
        param_data = params[param_name]

        if isinstance(param_data, dict):
            init_value = param_data["init"]
            end_value = param_data["end"]
            step_value = param_data.get("step", 1)

            if isinstance(init_value, (int, float)):
                param_values.append(
                    [
                        round(val / 10, 1)
                        for val in range(
                            int(init_value * 10),
                            int((end_value + step_value) * 10),
                            int(step_value * 10),
                        )
                    ]
                )
            elif isinstance(init_value, list) and all(
                isinstance(v, (int, float)) for v in init_value
            ):
                interpolated_values = _interpolate_values(init_value[0], end_value[0], step_value)
                param_values.append(
                    [(val, val + init_value[1] - init_value[0]) for val in interpolated_values]
                )

        elif isinstance(param_data, list):
            param_values.append(param_data)

    configs = list(itertools.product(*param_values))

    result = []
    for config_values in configs:
        config = dict(zip(param_names, config_values))
        result.append(config)

    return result


def search_workflow(ntokens, input_data_dir, dataset_ref, exp_param_settings, max_runs, campaign_id=None):
    cluster = LocalCluster(n_workers=1)
    scheduler = cluster.scheduler
    client = Client(scheduler.address)
    client.forward_logging()
    # Registering Flowcept's worker and scheduler adapters
    scheduler.add_plugin(FlowceptDaskSchedulerAdapter(scheduler))
    client.register_plugin(FlowceptDaskWorkerAdapter())
    exp_param_settings["dataset_ref"] = dataset_ref
    exp_param_settings["max_runs"] = max_runs
    exp_param_settings["input_data_dir"] = input_data_dir
    # Registering a Dask workflow in Flowcept's database
    search_wf_id = register_dask_workflow(client, used=exp_param_settings,
                                          workflow_name="model_search",
                                          campaign_id=campaign_id)
    print(f"workflow_id={search_wf_id}")

    configs = generate_configs(exp_param_settings)
    configs = [
        {**c, "ntokens": ntokens, "input_data_dir": input_data_dir, "workflow_id": search_wf_id, "campaign_id": campaign_id}
        for c in configs
    ]
    # Start Flowcept's Dask observer
    with Flowcept("dask") as f:
        for conf in configs[:max_runs]:  # Edit here to enable more runs
            t = client.submit(model_train, **conf)
            print(t.result())

        print("Done main loop. Closing dask...")
        client.close()  # This is to avoid generating errors
        cluster.close()  # These calls are needed closeouts to inform of workflow conclusion.
        print("Closed Dask. Closing Flowcept...")
    print("Closed.")
    return search_wf_id


def run_asserts_and_exports(campaign_id):
    from flowcept.commons.vocabulary import Status
    print("Now running all asserts...")
    """
    So far, this works as follows:
    Campaign:
        Data Prep Workflow
        Search Workflow

        Workflows:
            Data Prep Workflow
            Search workflow ->
              Module Layer Forward Train Workflow
              Module Layer Forward Test Workflow

    Tasks:
        Main workflow . Main model_train task (dask task) ->
            Main workflow . Epochs Whole Loop
                Main workflow . Loop Iteration Task
                    Module Layer Forward Train Workflow . Parent module forward tasks
                        Module Layer Forward Train Workflow . Children modules forward
            Module Layer Forward Test Workflow . Parent module forward tasks
                Module Layer Forward Test Workflow . Children modules forward tasks
    """
    campaign_workflows = Flowcept.db.query({"campaign_id": campaign_id}, collection="workflows")
    workflows_data = []
    assert len(campaign_workflows) == 4 - 1 # dataprep + model_search + 2 subworkflows for the model_seearch
    model_search_wf = dataprep_wf = None
    for w in campaign_workflows:
        workflows_data.append(w)
        if w["name"] == "model_search":
            model_search_wf = w
        elif w["name"] == "generate_wikitext_dataset":
            dataprep_wf = w
    assert dataprep_wf["generated"]["dataset_ref"] == model_search_wf["used"]["dataset_ref"]

    n_tasks_expected = 0
    model_train_tasks = Flowcept.db.query(
        {"workflow_id": model_search_wf_id, "activity_id": "model_train"})
    assert len(model_train_tasks) == model_search_wf["used"]["max_runs"]
    for t in model_train_tasks:
        n_tasks_expected += 1
        assert t["status"] == Status.FINISHED.value

        whole_loop = Flowcept.db.query(
            {"parent_task_id": t["task_id"], "subtype": "whole_loop"})[0]
        assert whole_loop["status"] == Status.FINISHED.value
        n_tasks_expected += 1
        iteration_tasks = Flowcept.db.query(
            {"parent_task_id": whole_loop["task_id"], "activity_id": "epochs_loop_iteration"})
        assert len(iteration_tasks) == t["used"]["epochs"]

        iteration_ids = set()
        for iteration_task in iteration_tasks:
            n_tasks_expected += 1
            iteration_ids.add(iteration_task["task_id"])
            assert iteration_task["status"] == Status.FINISHED.value

        if "parent" in TORCH_CAPTURE:

            parent_module_wfs = Flowcept.db.query({"parent_workflow_id": model_search_wf_id},
                                                  collection="workflows")
            assert len(parent_module_wfs) == 2 - 1  # train and test # TODO: train only for now

            for parent_module_wf in parent_module_wfs:
                workflows_data.append(parent_module_wf)
                parent_module_wf_id = parent_module_wf["workflow_id"]

                parent_forwards = Flowcept.db.query(
                    {"workflow_id": parent_module_wf_id, "activity_id": "TransformerModel"})

                assert len(parent_forwards)

                for parent_forward in parent_forwards:
                    n_tasks_expected += 1
                    assert parent_forward["workflow_id"] == parent_module_wf_id
                    assert parent_forward["used"]
                    assert parent_forward["status"] == Status.FINISHED.value
                    if parent_module_wf['custom_metadata']['model_step'] == 'test':
                        assert parent_forward["parent_task_id"] == t["task_id"]
                    elif parent_module_wf['custom_metadata']['model_step'] == 'train':
                        assert parent_module_wf["custom_metadata"]["model_profile"]
                        assert parent_forward[
                                   "parent_task_id"] in iteration_ids  # TODO: improve to test exact value

                    if "children" in TORCH_CAPTURE and parent_forward["parent_task_id"] in iteration_ids:
                        children_forwards = Flowcept.db.query(
                            {"parent_task_id": parent_forward["task_id"]})
                        assert len(children_forwards) == 4  # there are four children submodules # TODO get dynamically
                        for child_forward in children_forwards:
                            n_tasks_expected += 1
                            assert child_forward["status"] == Status.FINISHED.value
                            assert child_forward["workflow_id"] == parent_module_wf_id

    n_workflows_expected = len(campaign_workflows)
    return n_workflows_expected, n_tasks_expected


def save_files(campaign_id, n_workflows_expected, n_tasks_expected, output_dir="output_data"):
    os.makedirs(output_dir, exist_ok=True)
    best_task = Flowcept.db.query({"workflow_id": model_search_wf_id}, limit=1,
                                  sort=[("generated.val_loss", Flowcept.db.ASCENDING)])[0]
    best_model_obj_id = best_task["generated"]["best_obj_id"]
    model_args = best_task["used"].copy()
    # TODO: The wrapper is conflicting with the init arguments, that's why we need to copy & remove extra args. Needs to debug to improve.
    model_args.pop("batch_size", None)
    model_args.pop("eval_batch_size", None)
    model_args.pop("epochs", None)
    model_args.pop("lr", None)
    model_args.pop("input_data_dir", None)
    loaded_model = TransformerModel(**model_args, save_workflow=False)
    doc = Flowcept.db.load_torch_model(loaded_model, best_model_obj_id)
    print(doc)
    torch.save(loaded_model.state_dict(),
               f"{output_dir}/wf_{model_search_wf_id}_transformer_wikitext2.pth")
    workflows_file = f"{output_dir}/workflows_{uuid.uuid4()}.json"
    print(f"workflows_file = '{workflows_file}'")
    Flowcept.db.dump_to_file(filter={"campaign_id": campaign_id}, collection="workflows",
                             output_file=workflows_file)
    tasks_file = f"{output_dir}/tasks_{uuid.uuid4()}.parquet"
    print(f"tasks_file = '{tasks_file}'")
    Flowcept.db.dump_tasks_to_file_recursive(workflow_id=model_search_wf_id, output_file=tasks_file)

    return workflows_file, tasks_file


def main():

    _campaign_id = str(uuid.uuid4())
    print(f"Campaign id={_campaign_id}")
    input_data_dir = "input_data"
    tokenizer_type = "basic_english"
    subset_size = 10
    max_runs = 1
    epochs = 4
    exp_param_settings = {
        "batch_size": [20],
        "eval_batch_size": [10],
        "emsize": [200],
        "nhid": [200],
        "nlayers": [2],  # 2
        "nhead": [2],
        "dropout": [0.2],
        "epochs": [epochs],
        "lr": [0.1],
        "pos_encoding_max_len": [5000],
    }

    _dataprep_wf_id, dataprep_generated = dataprep_workflow(
        data_dir="input_data",
        campaign_id=_campaign_id,
        tokenizer_type=tokenizer_type,
        batch_size=exp_param_settings["batch_size"][0],
        eval_batch_size=exp_param_settings["eval_batch_size"][0],
        subset_size=subset_size)
    _search_wf_id = search_workflow(dataprep_generated["ntokens"], input_data_dir, dataprep_generated["dataset_ref"], exp_param_settings, max_runs, campaign_id=_campaign_id)

    return _campaign_id, _dataprep_wf_id, _search_wf_id, epochs, max_runs, dataprep_generated["train_n_batches"], dataprep_generated["val_n_batches"]


def asserts_on_saved_dfs(workflows_file, tasks_file, epochs, max_runs, n_batches_train, n_batches_eval, n_modules):

    workflows_df = pd.read_json(workflows_file)
    # Assert workflows dump
    assert len(workflows_df) == n_workflows_expected
    tasks_df = pd.read_parquet(tasks_file)
    print(len(tasks_df), n_tasks_expected)

    # TODO: save #n_batches for train, test, val individually
    search_tasks = max_runs
    whole_loop = 1
    at_every = INSTRUMENTATION.get("torch", {}).get("capture_at_every", 1)

    non_module_tasks = search_tasks+whole_loop+epochs
    parent_module_tasks = search_tasks*whole_loop*epochs*((n_batches_train*1)+(n_batches_eval*1))
    parent_module_tasks = parent_module_tasks/at_every
    expected_non_child_tasks = non_module_tasks + parent_module_tasks

    assert len(tasks_df[tasks_df.subtype != 'child_forward']) == expected_non_child_tasks

    expected_child_tasks = search_tasks * whole_loop * epochs * ((n_batches_train * n_modules) + (n_batches_eval * n_modules))
    expected_child_tasks = expected_child_tasks/at_every
    assert len(tasks_df[tasks_df.subtype == 'child_forward']) == expected_child_tasks

    number_of_captured_epochs = epochs/at_every
    expected_child_tasks_per_epoch = expected_child_tasks/number_of_captured_epochs

    with_used = 1*expected_child_tasks_per_epoch
    without_used = (number_of_captured_epochs-1)*expected_child_tasks_per_epoch

    assert len(tasks_df) == n_tasks_expected

    # Testing if only the first epoch got the inspection
    assert len(tasks_df[(tasks_df.subtype == 'parent_forward') & (tasks_df.used.str.contains('tensor'))]) == n_batches_train + n_batches_eval
    # Testing if capturing at every at_every epochs
    assert len(tasks_df[(tasks_df.subtype == 'child_forward') & (tasks_df.used == 'NaN')]) == without_used
    assert len(tasks_df[(tasks_df.subtype == 'child_forward') & (tasks_df.used != 'NaN')]) == with_used


if __name__ == "__main__":

    if not MONGO_ENABLED:
        print("This test is only available if Mongo is enabled.")
        sys.exit(0)

    campaign_id, dataprep_wf_id, model_search_wf_id, epochs, max_runs, n_batches_train, n_batches_eval = main()
    n_workflows_expected, n_tasks_expected = run_asserts_and_exports(campaign_id)
    workflows_file, tasks_file = save_files(campaign_id, n_workflows_expected=n_workflows_expected, n_tasks_expected=n_tasks_expected)
    asserts_on_saved_dfs(workflows_file, tasks_file, epochs, max_runs, n_batches_train, n_batches_eval, n_modules=4)
    print("Alright! Congrats.")

