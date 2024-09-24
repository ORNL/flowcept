import unittest
import itertools
import uuid

from flowcept import WorkflowObject, Flowcept

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.adapters.dask.dask_plugins import (
    register_dask_workflow,
)
from tests.adapters.dask_test_utils import (
    setup_local_dask_cluster,
    close_dask,
)

from tests.decorator_tests.ml_tests.llm_tests.llm_trainer import (
    get_wiki_text,
    model_train,
)


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
                interpolated_values = _interpolate_values(
                    init_value[0], end_value[0], step_value
                )
                param_values.append(
                    [
                        (val, val + init_value[1] - init_value[0])
                        for val in interpolated_values
                    ]
                )

        elif isinstance(param_data, list):
            param_values.append(param_data)

    configs = list(itertools.product(*param_values))

    result = []
    for config_values in configs:
        config = dict(zip(param_names, config_values))
        result.append(config)

    return result


class DecoratorDaskLLMTests(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(DecoratorDaskLLMTests, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    def test_llm(self):
        # Manually registering the DataPrep workflow (manual instrumentation)
        tokenizer = "toktok"  #  basic_english, moses, toktok
        dataset_prep_wf = WorkflowObject()
        dataset_prep_wf.workflow_id = f"prep_wikitext_tokenizer_{tokenizer}"
        dataset_prep_wf.used = {"tokenizer": tokenizer}
        ntokens, train_data, val_data, test_data = get_wiki_text(tokenizer)
        dataset_ref = f"{dataset_prep_wf.workflow_id}_{id(train_data)}_{id(val_data)}_{id(test_data)}"
        dataset_prep_wf.generated = {
            "ntokens": ntokens,
            "dataset_ref": dataset_ref,
            "train_data": id(train_data),
            "val_data": id(val_data),
            "test_data": id(test_data),
        }
        print(dataset_prep_wf)
        Flowcept.db.insert_or_update_workflow(dataset_prep_wf)

        # Automatically registering the Dask workflow
        train_wf_id = str(uuid.uuid4())
        client, cluster, consumer = setup_local_dask_cluster(
            exec_bundle=train_wf_id
        )
        register_dask_workflow(
            client, workflow_id=train_wf_id, used={"dataset_ref": dataset_ref}
        )

        print(f"Model_Train_Wf_id={train_wf_id}")
        exp_param_settings = {
            "batch_size": [20],
            "eval_batch_size": [10],
            "emsize": [200],
            "nhid": [200],
            "nlayers": [2],  # 2
            "nhead": [2],
            "dropout": [0.2],
            "epochs": [1],
            "lr": [0.1],
            "pos_encoding_max_len": [5000],
        }
        configs = generate_configs(exp_param_settings)
        outputs = []

        for conf in configs[:1]:
            conf.update(
                {
                    "ntokens": ntokens,
                    "train_data": train_data,
                    "val_data": val_data,
                    "test_data": test_data,
                    "workflow_id": train_wf_id,
                }
            )
            outputs.append(client.submit(model_train, **conf))

        for o in outputs:
            o.result()

        close_dask(client, cluster)
        consumer.stop()
