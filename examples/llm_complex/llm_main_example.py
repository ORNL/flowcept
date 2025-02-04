# The code in example file is based on:
# https://blog.paperspace.com/build-a-language-model-using-pytorch/
import itertools
import yaml
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


def search_workflow(ntokens, dataset_ref, train_data_path, val_data_path, test_data_path, exp_param_settings, max_runs, campaign_id=None):
    cluster = LocalCluster(n_workers=1)
    scheduler = cluster.scheduler
    client = Client(scheduler.address)
    client.forward_logging()
    # Registering Flowcept's worker and scheduler adapters
    client.register_plugin(FlowceptDaskSchedulerAdapter())
    client.register_plugin(FlowceptDaskWorkerAdapter())
    exp_param_settings["max_runs"] = max_runs
    exp_param_settings["train_data_path"] = train_data_path
    exp_param_settings["val_data_path"] = val_data_path
    exp_param_settings["test_data_path"] = test_data_path
    # Registering a Dask workflow in Flowcept's database
    search_wf_id = register_dask_workflow(client, used=exp_param_settings,
                                          workflow_name="model_search",
                                          campaign_id=campaign_id)
    print(f"workflow_id={search_wf_id}")

    configs = generate_configs(exp_param_settings)
    configs = [
        {**c, "ntokens": ntokens,
         "dataset_ref": dataset_ref,
         "train_data_path":train_data_path,
         "val_data_path": val_data_path,
         "test_data_path": test_data_path,
         "workflow_id": search_wf_id,
         "campaign_id": campaign_id}
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


def run_asserts_and_exports(campaign_id, model_search_wf_id):
    from flowcept.commons.vocabulary import Status
    print("Now running all asserts...")
    """
    # TODO revisit
    This works as follows:
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

    if INSTRUMENTATION.get("torch").get("epoch_loop") is None or INSTRUMENTATION.get("torch").get("batch_loop") is None:
        raise Exception("We can't assert this now.")

    at_every = INSTRUMENTATION.get("torch").get("capture_epochs_at_every", 1)
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
    assert dataprep_wf["generated"]["train_data_path"]
    assert dataprep_wf["generated"]["test_data_path"]
    assert dataprep_wf["generated"]["val_data_path"]

    parent_module_wfs = Flowcept.db.query({"parent_workflow_id": model_search_wf_id},
                                          collection="workflows")
    assert len(parent_module_wfs) == 1
    parent_module_wf = parent_module_wfs[0]
    workflows_data.append(parent_module_wf)
    parent_module_wf_id = parent_module_wf["workflow_id"]

    n_tasks_expected = 0
    model_train_tasks = Flowcept.db.query(
        {"workflow_id": model_search_wf_id, "activity_id": "model_train"})
    assert len(model_train_tasks) == model_search_wf["used"]["max_runs"]
    for t in model_train_tasks:
        n_tasks_expected += 1
        assert t["status"] == Status.FINISHED.value

        epoch_iteration_tasks = Flowcept.db.query(
            {"parent_task_id": t["task_id"], "activity_id": "epochs_loop_iteration"})
        assert len(epoch_iteration_tasks) == t["used"]["epochs"]

        epoch_iteration_ids = set()
        for epoch_iteration_task in epoch_iteration_tasks:
            n_tasks_expected += 1
            epoch_iteration_ids.add(epoch_iteration_task["task_id"])
            assert epoch_iteration_task["status"] == Status.FINISHED.value

            train_batch_iteration_tasks = Flowcept.db.query(
                {"parent_task_id": epoch_iteration_task["task_id"], "activity_id": "train_batch_iteration"})

            assert len(train_batch_iteration_tasks) > 0  # TODO: == number of train_batches

            eval_batch_iteration_tasks = Flowcept.db.query(
                {"parent_task_id": epoch_iteration_task["task_id"],
                 "activity_id": "eval_batch_iteration"})
            assert len(eval_batch_iteration_tasks) > 0  # TODO: == number of eval_batches

            batch_iteration_lst = [train_batch_iteration_tasks, eval_batch_iteration_tasks]
            for batch_iterations in batch_iteration_lst:

                for batch_iteration in batch_iterations:
                    n_tasks_expected += 1

                    if "parent" in INSTRUMENTATION.get("torch").get("what"):

                        parent_forwards = Flowcept.db.query(
                            {"workflow_id": parent_module_wf_id, "activity_id": "TransformerModel", "parent_task_id": batch_iteration["task_id"]})

                        if len(parent_forwards) == 0:
                            continue

                        assert len(parent_forwards) == 1
                        parent_forward = parent_forwards[0]

                        n_tasks_expected += 1
                        assert parent_forward["workflow_id"] == parent_module_wf_id
                        assert parent_forward["status"] == Status.FINISHED.value
                        assert parent_module_wf["custom_metadata"]["model_profile"]
                        assert parent_forward[
                                   "parent_task_id"] == batch_iteration["task_id"]

                        if "children" in INSTRUMENTATION.get("torch").get("what"):
                            children_forwards = Flowcept.db.query(
                                {"parent_task_id": parent_forward["task_id"]})

                            # We only have children_forward if:
                            # epoch == 1 or
                            # telemetry and epoch % at every == 0
                            curr_epoch = epoch_iteration_task["used"]["i"]
                            if  (curr_epoch == 0) or \
                                ("telemetry" in INSTRUMENTATION.get("torch").get("children_mode") and curr_epoch % at_every == 0):
                                assert len(children_forwards) == 4  # there are four children submodules # TODO get dynamically
                                for child_forward in children_forwards:
                                    n_tasks_expected += 1
                                    assert child_forward["status"] == Status.FINISHED.value
                                    assert child_forward["workflow_id"] == parent_module_wf_id
                            else:
                                assert len(children_forwards) == 0

    n_workflows_expected = len(campaign_workflows)
    return n_workflows_expected, n_tasks_expected


def save_files(mongo_dao, campaign_id, model_search_wf_id, output_dir="output_data"):
    os.makedirs(output_dir, exist_ok=True)
    best_task = Flowcept.db.query({"workflow_id": model_search_wf_id, "activity_id": "model_train"}, limit=1,
                                  sort=[("generated.test_loss", Flowcept.db.ASCENDING)])[0]
    best_model_obj_id = best_task["generated"]["best_obj_id"]
    model_args = best_task["used"].copy()
    # TODO: The wrapper is conflicting with the init arguments, that's why we need to copy & remove extra args. Needs to debug to improve.
    model_args.pop("batch_size", None)
    model_args.pop("eval_batch_size", None)
    model_args.pop("epochs", None)
    model_args.pop("lr", None)
    model_args.pop("train_data_path", None)
    model_args.pop("test_data_path", None)
    model_args.pop("val_data_path", None)
    model_args.pop("dataset_ref", None)
    loaded_model = TransformerModel(**model_args, save_workflow=False)
    doc = Flowcept.db.load_torch_model(loaded_model, best_model_obj_id)
    torch.save(loaded_model.state_dict(),
               f"{output_dir}/wf_{model_search_wf_id}_transformer_wikitext2.pth")

    print("Deleting best model from the database.")
    mongo_dao.delete_object_keys("object_id", [doc["object_id"]])

    workflows_file = f"{output_dir}/workflows_{uuid.uuid4()}.json"
    print(f"workflows_file = '{workflows_file}'")
    Flowcept.db.dump_to_file(filter={"campaign_id": campaign_id}, collection="workflows",
                             output_file=workflows_file)
    tasks_file = f"{output_dir}/tasks_{uuid.uuid4()}.parquet"
    print(f"tasks_file = '{tasks_file}'")

    mapping_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'custom_provenance_id_mapping.yaml')
    with open(mapping_path) as f:
        mapping = yaml.safe_load(f)
    Flowcept.db.dump_tasks_to_file_recursive(workflow_id=model_search_wf_id, output_file=tasks_file, mapping=mapping)

    return workflows_file, tasks_file


def run_campaign():

    _campaign_id = str(uuid.uuid4())
    print(f"Campaign id={_campaign_id}")
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

    _search_wf_id = search_workflow(dataprep_generated["ntokens"], dataprep_generated["dataset_ref"], dataprep_generated["train_data_path"], dataprep_generated["val_data_path"], dataprep_generated["test_data_path"], exp_param_settings, max_runs, campaign_id=_campaign_id)

    return _campaign_id, _dataprep_wf_id, _search_wf_id, epochs, max_runs, dataprep_generated["train_n_batches"], dataprep_generated["val_n_batches"]


def asserts_on_saved_dfs(mongo_dao, workflows_file, tasks_file, n_workflows_expected, n_tasks_expected, epoch_iterations, max_runs, n_batches_train, n_batches_eval, n_modules):
    workflows_df = pd.read_json(workflows_file)
    # Assert workflows dump
    assert len(workflows_df) == n_workflows_expected
    tasks_df = pd.read_parquet(tasks_file)
    print(len(tasks_df), n_tasks_expected)
    #assert len(tasks_df) == n_tasks_expected

    # TODO: save #n_batches for train, test, val individually
    search_tasks = max_runs
    at_every = INSTRUMENTATION.get("torch").get("capture_epochs_at_every", 1)

    batch_iteration_tasks = epoch_iterations * (n_batches_train + n_batches_eval)
    non_module_tasks = search_tasks + epoch_iterations + batch_iteration_tasks

    parent_module_tasks = batch_iteration_tasks
    parent_module_tasks = parent_module_tasks/at_every
    expected_non_child_tasks = non_module_tasks + parent_module_tasks

    assert len(tasks_df[tasks_df.subtype != 'child_forward']) == expected_non_child_tasks

    number_of_captured_epochs = epoch_iterations / at_every

    if "telemetry" in INSTRUMENTATION.get("torch").get("children_mode"):
        expected_child_tasks = search_tasks * epoch_iterations * (
                    (n_batches_train * n_modules) + (n_batches_eval * n_modules))
        expected_child_tasks = expected_child_tasks/at_every
        expected_child_tasks_per_epoch = expected_child_tasks / number_of_captured_epochs
        with_used = 1 * expected_child_tasks_per_epoch
        without_used = (number_of_captured_epochs - 1) * expected_child_tasks_per_epoch
    elif "tensor_inspection" in INSTRUMENTATION.get("torch").get("children_mode"):
        expected_child_tasks = search_tasks * 1 * (
                    (n_batches_train * n_modules) + (n_batches_eval * n_modules))
        expected_child_tasks_per_epoch = expected_child_tasks
        with_used = 1 * expected_child_tasks_per_epoch
        without_used = 0
    else:
        raise NotImplementedError("Needs to implement for lightweight")

    # Testing if only the first epoch got the inspection
    assert len(tasks_df[(tasks_df.subtype == 'parent_forward') & (tasks_df.used.str.contains('tensor'))]) == n_batches_train + n_batches_eval

    if "children" in INSTRUMENTATION.get("torch").get("what"):
        assert len(tasks_df[tasks_df.subtype == 'child_forward']) == expected_child_tasks
        assert non_module_tasks + parent_module_tasks + expected_child_tasks == len(tasks_df)
        # Testing if capturing at every at_every epochs
        assert len(tasks_df[(tasks_df.subtype == 'child_forward') & (
                    tasks_df.used == 'NaN')]) == without_used
        assert len(
            tasks_df[(tasks_df.subtype == 'child_forward') & (tasks_df.used != 'NaN')]) == with_used

    task_ids = list(tasks_df["task_id"].unique())
    workflow_ids = list(workflows_df["workflow_id"].unique())
    print("Deleting generated data in MongoDB")
    mongo_dao.delete_task_keys("task_id", task_ids)
    mongo_dao.delete_workflow_keys("workflow_id", workflow_ids)


def verify_number_docs_in_db(mongo_dao, n_tasks=None, n_wfs=None, n_objects=None):
    _n_tasks = mongo_dao.count_tasks()
    _n_wfs = mongo_dao.count_workflows()
    _n_objects = mongo_dao.count_objects()

    if n_tasks:
        if n_tasks != _n_tasks:
            raise Exception("Number of tasks now is different than when we started this campaign.")
        else:
            print("Good, #tasks are equal to the beginning!")

    if n_wfs:
        if n_wfs != _n_wfs:
            raise Exception("Number of workflows now is different than when we started this campaign.")
        else:
            print("Good, #workflows are equal to the beginning!")

    if n_objects:
        if n_objects != _n_objects:
            raise Exception("Number of object now is different than when we started this campaign.")
        else:
            print("Good, #objects are equal to the beginning!")

    return _n_tasks, _n_wfs, _n_objects



def main():

    print("TORCH SETTINGS: " + str(INSTRUMENTATION.get("torch")))

    from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO
    mongo_dao = MongoDBDAO(create_indices=False)

    n_tasks, n_wfs, n_objects = verify_number_docs_in_db(mongo_dao)

    campaign_id, dataprep_wf_id, model_search_wf_id, epochs, max_runs, n_batches_train, n_batches_eval = run_campaign()

    n_workflows_expected, n_tasks_expected = run_asserts_and_exports(campaign_id, model_search_wf_id)
    workflows_file, tasks_file = save_files(mongo_dao, campaign_id, model_search_wf_id)
    asserts_on_saved_dfs(mongo_dao, workflows_file, tasks_file, n_workflows_expected, n_tasks_expected,
                         epochs, max_runs, n_batches_train, n_batches_eval, n_modules=4)
    verify_number_docs_in_db(mongo_dao, n_tasks, n_wfs, n_objects)
    print("Alright! Congrats.")


if __name__ == "__main__":

    if not MONGO_ENABLED:
        print("This test is only available if Mongo is enabled.")
        sys.exit(0)

    main()
    sys.exit(0)

