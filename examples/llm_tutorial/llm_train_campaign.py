# The code in example file is based on:
# https://blog.paperspace.com/build-a-language-model-using-pytorch/
import argparse
import json
import sys
import itertools
import uuid
import pandas as pd
from time import time

from llm_dataprep import dataprep_workflow
from llm_model import model_train
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


def search_workflow(ntokens, dataset_ref, train_data_path, val_data_path, test_data_path, workflow_params, campaign_id=None, scheduler_file=None, start_dask_cluster=False, with_persistence=True, with_flowcept=True, dask_map_gpus=False):
    client, cluster = start_dask(with_flowcept)
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
         "with_persistence": with_persistence,
         "with_flowcept": with_flowcept,
         "campaign_id": campaign_id,
         "dask_map_gpus": dask_map_gpus
         }
        for c in configs
    ]

    max_runs = workflow_params.get("max_runs", None)
    configs = configs[:max_runs]
    
    print(f"Size of configs: {len(configs)}")

    f = None
    search_wf_id = None
    if with_flowcept:
        # Start Flowcept's Dask observer
        prov_args = workflow_params.copy()
        prov_args["n_configs"] = len(configs)
        f = Flowcept("dask", campaign_id=campaign_id, start_persistence=with_persistence, workflow_name="SearchWorkflow", workflow_args=prov_args, dask_client=client, delete_buffer_file=False).start()
        search_wf_id = Flowcept.current_workflow_id
        print(f"search_workflow_id={search_wf_id}")

    t1 = time()
    tasks = []
    for conf in configs:  # Edit here to enable more runs
        tasks.append(client.submit(model_train, workflow_id=search_wf_id, **conf))

    for t in tasks:
        print(t.result())

    t2 = time()
    with open("time.txt", "w") as file:
        file.write(f"{t2 - t1}\n")

    print("Done main loop. Closing dask.")
    close_dask(client, cluster, f)
    return search_wf_id, len(configs)


def start_dask(with_flowcept=True):
    from distributed import Client
    from distributed import LocalCluster
    cluster = LocalCluster(n_workers=1)
    scheduler = cluster.scheduler
    client = Client(scheduler.address)
    client.forward_logging()
    # Registering Flowcept's worker adapters
    if with_flowcept:
        from flowcept.flowceptor.adapters.dask.dask_plugins import FlowceptDaskWorkerAdapter
        client.register_plugin(FlowceptDaskWorkerAdapter())

    return client, cluster


def close_dask(client, cluster, _flowcept=None):
    try:
        print("Closing dask...")
        client.close()
        cluster.close()
        print("Dask closed.")
        if _flowcept:
            print("Now closing flowcept consumer...")
            _flowcept.stop()
            print("Flowcept consumer closed.")
    except Exception as e:
        print(e)


def run_campaign(workflow_params, campaign_id=None, start_dask_cluster=False, with_persistence=True, with_flowcept=True):

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
        subset_size=subset_size,
        with_persistence=with_persistence)

    _search_wf_id, n_configs = search_workflow(dataprep_generated["ntokens"], dataprep_generated["dataset_ref"], dataprep_generated["train_data_path"], dataprep_generated["val_data_path"], dataprep_generated["test_data_path"], workflow_params, campaign_id=_campaign_id, start_dask_cluster=start_dask_cluster, with_persistence=with_persistence, with_flowcept=with_flowcept)

    return _campaign_id, _dataprep_wf_id, _search_wf_id, dataprep_generated["train_n_batches"], dataprep_generated["val_n_batches"], n_configs


def parse_args():
    parser = argparse.ArgumentParser(description="Submit Dask workflow.")

    arguments = parser.add_argument_group("arguments")
    arguments.add_argument("--rep-dir", metavar="D", default="./output_data", help="Job's repetition directory")
    arguments.add_argument("--campaign-id", metavar="D", default=None, help="Campaign Id")
    true_values = {"true", "t", "1", "yes", "y"}
    arguments.add_argument(
        "--with-persistence",
        type=lambda v: v.lower() in true_values,
        default=True,
        help=f"Store data in MongoDB (accepts: {', '.join(true_values)})",
    )
    arguments.add_argument(
        "--with-flowcept",
        type=lambda v: v.lower() in true_values,
        default=True,
        help=f"Use flowcept dask plugin (accepts: {', '.join(true_values)})",
    )

    arguments.add_argument("--start-dask-cluster", action="store_true", default=False, help="Start the dask cluster before execution. Use only for tests and not for real experiments")

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
        "max_runs": None,
        "random_seed": 0,
        "tokenizer_type": "basic_english",   # spacy, moses, toktok, revtok, subword
    }

    arguments.add_argument(
        "--workflow-params",
        metavar="D",
        default=json.dumps(default_exp_param_settings),
        help="Workflow Parameters as a stringified dictionary",
    )
    args, _ = parser.parse_known_args()  # Ignore unknown arguments

    if not args.with_flowcept:
        args.with_persistence = False

    return args


def main():

    args = parse_args()
    print("Arguments:", args)
    workflow_params = json.loads(args.workflow_params)
    workflow_params["with_persistence"] = args.with_persistence
    print("TORCH SETTINGS: " + str(INSTRUMENTATION.get("torch")))
    run_campaign(workflow_params, campaign_id=args.campaign_id, start_dask_cluster=args.start_dask_cluster, with_persistence=args.with_persistence, with_flowcept=args.with_flowcept)

    print("Alright! Congrats.")
    return 1


if __name__ == "__main__":
    main()
    sys.exit(0)

