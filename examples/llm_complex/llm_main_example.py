# The code in example file is based on:
# https://blog.paperspace.com/build-a-language-model-using-pytorch/
import argparse
import json
import sys
import itertools
import yaml
import os
import uuid
import pandas as pd
import torch

from examples.llm_complex.llm_dataprep import dataprep_workflow
from examples.llm_complex.llm_model import model_train, TransformerModel
from flowcept.flowceptor.adapters.dask.dask_plugins import register_dask_workflow
from flowcept.configs import MONGO_ENABLED, INSTRUMENTATION
from flowcept import Flowcept



def generate_configs(params: dict):
    """
    Generate a list of configurations by computing the Cartesian product of list-valued parameters
    while keeping constant parameters unchanged.

    Parameters
    ----------
    params : dict
        A dictionary where keys are parameter names and values can be either:
        - A list of possible values (for parameters to be expanded in the cross-product).
        - A single value (for constant parameters that remain unchanged across configurations).

    Returns
    -------
    list of dict
        A list of dictionaries, where each dictionary represents a unique configuration
        formed by combining the cross-product of list-valued parameters with the constant parameters.

    Examples
    --------
    >>> params = {
    ...     "a": [1, 2],
    ...     "b": [3, 4],
    ...     "c": "fixed"
    ... }
    >>> generate_configs(params)
    [{'a': 1, 'b': 3, 'c': 'fixed'},
     {'a': 1, 'b': 4, 'c': 'fixed'},
     {'a': 2, 'b': 3, 'c': 'fixed'},
     {'a': 2, 'b': 4, 'c': 'fixed'}]
    """
    result = []
    expanded_lists = []
    constants = {}
    for p in params:
        vals = params[p]
        if isinstance(vals, list):
            expanded = [{p: v} for v in vals]
            expanded_lists.append(expanded)
        else:
            constants[p] = vals

    cross_product = [{k: v for d in combo for k, v in d.items()}
                     for combo in itertools.product(*expanded_lists)]
    for c in cross_product:
        config = c.copy()
        config.update(constants)
        result.append(config)
    return result


def search_workflow(ntokens, dataset_ref, train_data_path, val_data_path, test_data_path, workflow_params, campaign_id=None, scheduler_file=None):
    client, cluster = start_dask(scheduler_file)
    workflow_params["train_data_path"] = train_data_path
    workflow_params["val_data_path"] = val_data_path
    workflow_params["test_data_path"] = test_data_path

    configs = generate_configs(workflow_params)
    configs = [
        {**c, "ntokens": ntokens,
         "dataset_ref": dataset_ref,
         "train_data_path": train_data_path,
         "val_data_path": val_data_path,
         "test_data_path": test_data_path,
         "campaign_id": campaign_id}
        for c in configs
    ]

    # Start Flowcept's Dask observer
    with Flowcept("dask"):

        # Registering a Dask workflow in Flowcept's database
        search_wf_id = register_dask_workflow(client, used=workflow_params,
                                              workflow_name="model_search",
                                              campaign_id=campaign_id)
        print(f"search_workflow_id={search_wf_id}")

        max_runs = workflow_params.get("max_runs", None)

        for conf in configs[:max_runs]:  # Edit here to enable more runs
            t = client.submit(model_train, workflow_id=search_wf_id, **conf)
            print(t.result())

        print("Done main loop. Closing dask...")
        close_dask(client, cluster, scheduler_file)
        print("Closed Dask. Closing Flowcept...")
        print("Closed.")
    return search_wf_id


def start_dask(scheduler_file):
    from distributed import Client
    from flowcept.flowceptor.adapters.dask.dask_plugins import FlowceptDaskWorkerAdapter
    if scheduler_file is None:
        from distributed import LocalCluster
        cluster = LocalCluster(n_workers=1)
        scheduler = cluster.scheduler
        client = Client(scheduler.address)
        client.forward_logging()
        # Registering Flowcept's worker adapters
        client.register_plugin(FlowceptDaskWorkerAdapter())
    else:
        # If scheduler file is provided, this cluster is not managed in this code.
        client = Client(scheduler_file=scheduler_file)
        client.register_plugin(FlowceptDaskWorkerAdapter())
        cluster = None
    return client, cluster


def close_dask(client, cluster, scheduler_file=None):
    if scheduler_file is None:
        client.close()
        cluster.close()
    else:
        client.close()
        client.shutdown()

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

    mswf = Flowcept.db.query({"workflow_id": model_search_wf_id}, collection="workflows")[0]
    assert model_search_wf == mswf

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
    # TODO: The wrapper is conflicting with the init arguments, that's why we need to copy & remove extra args. Needs to debug to improve. Do not try to inspect signature. It's hard, ugly, and will likely not going to work. If it does, we'll change it later anyway.
    model_args.pop("batch_size", None)
    model_args.pop("eval_batch_size", None)
    model_args.pop("epochs", None)
    model_args.pop("lr", None)
    model_args.pop("input_data_dir", None)
    model_args.pop("train_data_path", None)
    model_args.pop("test_data_path", None)
    model_args.pop("val_data_path", None)
    model_args.pop("dataset_ref", None)
    model_args.pop("subset_size", None)
    model_args.pop("tokenizer_type", None)
    delete_after_run = model_args.pop("delete_after_run", True)
    model_args.pop("max_runs", None)
    loaded_model = TransformerModel(**model_args, save_workflow=False)
    doc = Flowcept.db.load_torch_model(loaded_model, best_model_obj_id)
    torch.save(loaded_model.state_dict(),
               f"{output_dir}/wf_{model_search_wf_id}_transformer_wikitext2.pth")

    if delete_after_run:
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


def run_campaign(workflow_params, campaign_id=None):

    _campaign_id = campaign_id or str(uuid.uuid4())
    print(f"Campaign id={_campaign_id}")
    tokenizer_type = workflow_params["tokenizer_type"]
    subset_size = workflow_params.get("subset_size", None)

    _dataprep_wf_id, dataprep_generated = dataprep_workflow(
        data_dir=workflow_params["input_data_dir"],
        campaign_id=_campaign_id,
        tokenizer_type=tokenizer_type,
        batch_size=workflow_params["batch_size"],
        eval_batch_size=workflow_params["eval_batch_size"],
        subset_size=subset_size)

    _search_wf_id = search_workflow(dataprep_generated["ntokens"], dataprep_generated["dataset_ref"], dataprep_generated["train_data_path"], dataprep_generated["val_data_path"], dataprep_generated["test_data_path"], workflow_params, campaign_id=_campaign_id)

    return _campaign_id, _dataprep_wf_id, _search_wf_id, dataprep_generated["train_n_batches"], dataprep_generated["val_n_batches"]


def asserts_on_saved_dfs(mongo_dao, workflows_file, tasks_file, n_workflows_expected, n_tasks_expected, epoch_iterations, max_runs, n_batches_train, n_batches_eval, n_modules, delete_after_run):
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

    if delete_after_run:
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



def parse_args():
    parser = argparse.ArgumentParser(description="Submit Dask workflow.")

    arguments = parser.add_argument_group("arguments")
    arguments.add_argument("--scheduler-file", metavar="S", default=None, help="Dask's scheduler file")
    arguments.add_argument("--rep-dir", metavar="D", default=".", help="Job's repetition directory")
    arguments.add_argument("--workflow-id", metavar="D", default=None, help="Wf Id")
    arguments.add_argument("--campaign-id", metavar="D", default=None, help="Campaign Id")
    default_exp_param_settings = {
        "input_data_dir": "./input_data",
        "batch_size": 20,
        "eval_batch_size": 10,
        "emsize": [200],
        "nhid": [200],
        "nlayers": [2],  # 2
        "nhead": [2],
        "dropout": [0.2],
        "lr": [0.1],
        "pos_encoding_max_len": [5000],
        "subset_size": 10,
        "epochs": 4,
        "max_runs": 1,
        "delete_after_run": True,
        "tokenizer_type": "basic_english",   # spacy, moses, toktok, revtok, subword
    }

    arguments.add_argument(
        "--workflow-params",
        metavar="D",
        default=json.dumps(default_exp_param_settings),
        help="Workflow Parameters as a stringified dictionary",
    )
    args, _ = parser.parse_known_args()  # Ignore unknown arguments
    return args

def main():

    args = parse_args()
    print(args)
    workflow_params = json.loads(args.workflow_params)

    from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO
    mongo_dao = MongoDBDAO(create_indices=False)
    print("TORCH SETTINGS: " + str(INSTRUMENTATION.get("torch")))
    n_tasks, n_wfs, n_objects = verify_number_docs_in_db(mongo_dao)

    campaign_id, dataprep_wf_id, model_search_wf_id, n_batches_train, n_batches_eval = run_campaign(workflow_params)

    n_workflows_expected, n_tasks_expected = run_asserts_and_exports(campaign_id, model_search_wf_id)
    workflows_file, tasks_file = save_files(mongo_dao, campaign_id, model_search_wf_id)
    asserts_on_saved_dfs(mongo_dao, workflows_file, tasks_file, n_workflows_expected, n_tasks_expected,
                         workflow_params["epochs"], workflow_params["max_runs"], n_batches_train, n_batches_eval,
                         n_modules=4, delete_after_run=workflow_params["delete_after_run"])
    verify_number_docs_in_db(mongo_dao, n_tasks, n_wfs, n_objects)

    print("Alright! Congrats.")


if __name__ == "__main__":

    if not MONGO_ENABLED:
        print("This test is only available if Mongo is enabled.")
        sys.exit(0)

    main()
    sys.exit(0)

