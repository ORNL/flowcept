import unittest
import pickle
import os
import random

import pytest

pytest.importorskip("torch")

import torch
import torch.nn as nn
import torch.optim as optim

from flowcept import Flowcept
from flowcept.configs import MONGO_ENABLED
from flowcept.commons.vocabulary import ML_Types
from flowcept.instrumentation.flowcept_task import flowcept_task, get_current_context_task_id


def _set_reproducibility(seed=0):
    """Apply deterministic settings and return one reproducibility dict."""
    reproducibility = {}
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch, "use_deterministic_algorithms"):
        torch.use_deterministic_algorithms(True, warn_only=True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    reproducibility["seed"] = seed
    reproducibility["python_random_seeded"] = True
    reproducibility["torch_manual_seeded"] = True
    reproducibility["torch_cuda_manual_seeded"] = torch.cuda.is_available()
    reproducibility["torch_deterministic_algorithms"] = (
        torch.are_deterministic_algorithms_enabled()
        if hasattr(torch, "are_deterministic_algorithms_enabled")
        else True
    )
    reproducibility["torch_cudnn_deterministic"] = (
        bool(getattr(torch.backends.cudnn, "deterministic", False)) if hasattr(torch.backends, "cudnn") else False
    )
    reproducibility["torch_cudnn_benchmark"] = (
        bool(getattr(torch.backends.cudnn, "benchmark", False)) if hasattr(torch.backends, "cudnn") else False
    )
    return reproducibility


def shape_args_handler(*args, **kwargs):
    """Capture tensor values as shape metadata for provenance payloads."""
    def _shape_key(name):
        return name if name.endswith("_shape") else f"{name}_shape"

    handled = {}
    for i, arg in enumerate(args):
        key = f"arg_{i}"
        if isinstance(arg, torch.Tensor):
            handled[_shape_key(key)] = tuple(arg.shape)
        else:
            handled[key] = arg
    for key, value in kwargs.items():
        if isinstance(value, torch.Tensor):
            handled[_shape_key(key)] = tuple(value.shape)
        else:
            handled[key] = value
    return handled


class SingleLayerPerceptron(nn.Module):
    def __init__(self, input_size, **kwargs):
        super().__init__()
        self.layer = nn.Linear(input_size, 1)

    def forward(self, x):
        return torch.sigmoid(self.layer(x))


@flowcept_task(
    subtype=ML_Types.DATA_PREP,
    args_handler=shape_args_handler,
    output_names=["x_train_shape", "y_train_shape", "x_val_shape", "y_val_shape", "dataset_id"],
)
def get_dataset(n_samples, split_ratio):
    """Generate a toy binary classification dataset."""
    generator = torch.Generator().manual_seed(torch.initial_seed())
    x = torch.cat(
        [
            torch.randn(n_samples // 2, 2, generator=generator) + 2,
            torch.randn(n_samples // 2, 2, generator=generator) - 2,
        ]
    )
    y = torch.cat([torch.zeros(n_samples // 2), torch.ones(n_samples // 2)]).unsqueeze(1)
    n_train = int(n_samples * split_ratio)
    x_train, x_val = x[:n_train], x[n_train:]
    y_train, y_val = y[:n_train], y[n_train:]
    dataset_task_id = get_current_context_task_id()
    custom_metadata = {"n_samples": n_samples, "split_ratio": split_ratio}
    dataset_object_id = Flowcept.db.save_or_update_dataset(
        object={
            "x_train": x_train,
            "y_train": y_train,
            "x_val": x_val,
            "y_val": y_val,
        },
        task_id=dataset_task_id,
        custom_metadata=custom_metadata,
        save_data_in_collection=True,
        pickle=True,
        control_version=True,
    )
    return x_train, y_train, x_val, y_val, dataset_object_id


def validate(model, criterion, x_val, y_val):
    """Evaluate validation loss and accuracy."""
    model.eval()
    with torch.no_grad():
        outputs = model(x_val)
        loss = criterion(outputs, y_val)
        predictions = outputs.round()
        accuracy = (predictions.eq(y_val).sum().item()) / y_val.size(0)
    return loss.item(), accuracy


@flowcept_task(subtype=ML_Types.LEARNING)
def train_and_validate(
    n_input_neurons,
    epochs,
    x_train,
    y_train,
    x_val,
    y_val,
    dataset_id=None,
    checkpoint_check=2,
    learning_rate=0.1,
    config_id=None,
    torch_only=False,
):
    """Train a perceptron and return validation metrics.

    When ``torch_only=True``, only PyTorch-model persistence is performed.
    """
    model = SingleLayerPerceptron(input_size=n_input_neurons, get_profile=True)
    criterion = nn.BCELoss()
    optimizer = optim.SGD(model.parameters(), lr=learning_rate)
    best_val_loss = float("inf")
    ml_model_object_id = None
    torch_model_object_id = None
    current_task_id = get_current_context_task_id()
    x_train_cfg = x_train[:, :n_input_neurons]
    x_val_cfg = x_val[:, :n_input_neurons]

    for epoch in range(1, epochs + 1):
        model.train()
        outputs = model(x_train_cfg)
        loss = criterion(outputs, y_train)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        current_val_loss, _ = validate(model, criterion, x_val_cfg, y_val)

        if epoch % checkpoint_check == 0 and current_val_loss < best_val_loss:
            best_val_loss = current_val_loss
            custom_metadata = {
                "loss": best_val_loss,
                "checkpoint_epoch": epoch,
                "learning_rate": learning_rate,
                "n_input_neurons": n_input_neurons,
            }
            if config_id is not None:
                custom_metadata["config_id"] = config_id
            torch_model_object_id = Flowcept.db.save_or_update_torch_model(
                model=model,
                object_id=torch_model_object_id,
                task_id=current_task_id,
                custom_metadata=custom_metadata,
                control_version=True,
            )
            if not torch_only:
                ml_model_object_id = Flowcept.db.save_or_update_ml_model(
                    object=model.state_dict(),
                    object_id=ml_model_object_id,
                    task_id=current_task_id,
                    custom_metadata=custom_metadata,
                    save_data_in_collection=True,
                    pickle=True,
                    control_version=True,
                )

    final_val_loss, final_val_accuracy = validate(model, criterion, x_val_cfg, y_val)
    result = {
        "val_loss": final_val_loss,
        "val_accuracy": final_val_accuracy,
        "torch_model_object_id": torch_model_object_id,
        "best_val_loss": best_val_loss,
        "config_id": config_id,
    }
    if not torch_only:
        result["ml_model_object_id"] = ml_model_object_id
    return result


@flowcept_task(subtype=ML_Types.MODEL_SELECTION)
def select_best_model(workflow_id):
    """Select the best model object for a workflow by minimal recorded loss."""
    best_doc = Flowcept.db.query(
        collection="objects",
        filter={
            "workflow_id": workflow_id,
            "object_type": "ml_model",
            "custom_metadata.loss": {"$exists": True},
        },
        sort=[("custom_metadata.loss", 1)],
        limit=1,
    )[0]
    Flowcept.db.update_object_metadata(
        object_id=best_doc["object_id"],
        tags=["best"],
        control_version=True
    )
    return {
        "selected_model_object_id": best_doc["object_id"],
        "selected_loss": best_doc["custom_metadata"]["loss"],
        "selected_config_id": best_doc["custom_metadata"]["config_id"],
    }


def run_training(n_samples, split_ratio, n_input_neurons, epochs):
    """Perceptron training entrypoint."""
    # Data Prep:
    x_train, y_train, x_val, y_val, dataset_id = get_dataset(n_samples, split_ratio)

    # Train and Validate:
    result = train_and_validate(n_input_neurons, epochs, x_train, y_train, x_val, y_val, dataset_id=dataset_id)
    return result


def assert_single_inference_shape(model, sample):
    """Run a single inference and validate expected output shape."""
    model.eval()
    with torch.no_grad():
        pred = model(sample)
    assert pred.shape == (1, 1)


def asserts(tasks):
    assert tasks is not None
    assert len(tasks) > 0

    dataset_task = next((t for t in tasks if t.get("activity_id") == "get_dataset"), None)
    assert dataset_task is not None
    assert dataset_task.get("subtype") == ML_Types.DATA_PREP
    generated = dataset_task.get("generated", {})
    assert tuple(generated.get("x_train_shape", ())) == (96, 2)
    assert tuple(generated.get("y_train_shape", ())) == (96, 1)
    assert tuple(generated.get("x_val_shape", ())) == (24, 2)
    assert tuple(generated.get("y_val_shape", ())) == (24, 1)

    train_task = next((t for t in tasks if t.get("activity_id") == "train_and_validate"), None)
    assert train_task is not None
    assert train_task.get("subtype") == ML_Types.LEARNING
    train_generated = train_task.get("generated", {})
    ml_model_object_id = train_generated.get("ml_model_object_id")
    torch_model_object_id = train_generated.get("torch_model_object_id")
    assert ml_model_object_id is not None
    assert torch_model_object_id is not None

    versions = Flowcept.db.get_object_history(ml_model_object_id)
    assert len(versions) > 0
    for version_doc in versions:
        assert version_doc.get("task_id") == train_task.get("task_id")
        assert version_doc.get("custom_metadata") is not None
        assert "loss" in version_doc["custom_metadata"]
    losses = [v["custom_metadata"]["loss"] for v in versions]
    assert all(losses[i] <= losses[i + 1] for i in range(len(losses) - 1))
    assert versions[0]["version"] == len(versions) - 1

    torch_versions = Flowcept.db.get_object_history(torch_model_object_id)
    assert len(torch_versions) > 0
    for version_doc in torch_versions:
        assert version_doc.get("task_id") == train_task.get("task_id")
        assert version_doc.get("custom_metadata") is not None
        assert "loss" in version_doc["custom_metadata"]
        assert "model_profile" in version_doc["custom_metadata"]
        model_profile = version_doc["custom_metadata"]["model_profile"]
        assert isinstance(model_profile, dict)
        assert "params" in model_profile
        assert "n_modules" in model_profile
        assert "max_width" in model_profile
        assert "model_repr" in model_profile
    torch_losses = [v["custom_metadata"]["loss"] for v in torch_versions]
    assert all(torch_losses[i] <= torch_losses[i + 1] for i in range(len(torch_losses) - 1))
    assert torch_versions[0]["version"] == len(torch_versions) - 1

    assert len(torch_versions) == len(versions)

    dataset_docs = Flowcept.db.dataset_query(
        filter={
            "object_type": "dataset",
            "task_id": dataset_task.get("task_id"),
            "workflow_id": Flowcept.current_workflow_id,
        }
    )
    assert dataset_docs is not None
    assert len(dataset_docs) > 0
    dataset_blob = Flowcept.db.get_dataset(dataset_docs[0]["object_id"])
    assert dataset_blob is not None
    assert dataset_blob.object_type == "dataset"
    assert dataset_blob.task_id == dataset_task.get("task_id")
    assert dataset_blob.workflow_id == Flowcept.current_workflow_id

    workflows = Flowcept.db.query({"campaign_id": Flowcept.campaign_id}, collection="workflows")
    assert any(wf.get("name") == "Perceptron Train" for wf in workflows)
    assert any(wf.get("subtype") == ML_Types.WORKFLOW for wf in workflows)
    return ml_model_object_id, torch_model_object_id


class SingleLayerPerceptronTests(unittest.TestCase):

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_single_layer_perceptron_example_flow(self):
        params = {
            "n_samples": 120,
            "split_ratio": 0.8,
            "n_input_neurons": 2,
            "epochs": 6,
        }

        reproducibility = _set_reproducibility(seed=42)

        with Flowcept(
            workflow_name="Perceptron Train",
            workflow_subtype=ML_Types.WORKFLOW,
            workflow_args=reproducibility,
        ):
            run_training(**params)

        tasks = Flowcept.db.get_tasks_from_current_workflow()

        ml_model_object_id, torch_model_object_id = asserts(tasks)

        sample = torch.randn(1, params["n_input_neurons"])

        # Path 1: generic ml_model object saved with pickle=True (state_dict payload).
        best_ml_model_blob = Flowcept.db.get_ml_model(ml_model_object_id)
        ml_state_dict = pickle.loads(best_ml_model_blob.data)
        ml_model = SingleLayerPerceptron(input_size=params["n_input_neurons"])
        ml_model.load_state_dict(ml_state_dict)
        assert_single_inference_shape(ml_model, sample)

        # Path 2: torch-specific state_dict save/load API.
        reloaded_torch_model = SingleLayerPerceptron(input_size=params["n_input_neurons"])
        Flowcept.db.load_torch_model(reloaded_torch_model, torch_model_object_id)
        self.assert_model_metadata(reloaded_torch_model, torch_model_object_id)
        assert_single_inference_shape(reloaded_torch_model, sample)

        self.assert_provenance_reports(
            workflow_id=Flowcept.current_workflow_id,
            workflow_title="Perceptron Train",
            expect_aggregation_method=False,
            expected_activity_lines=[
                "- **get_dataset** (subtype=`dataprep`)",
                "- **train_and_validate** (subtype=`learning`)",
            ],
            expected_content_lines=[],
        )

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_single_layer_perceptron_gridsearch_torch_only(self):
        run_data = self.run_gridsearch_experiment()
        self.assert_gridsearch_experiment(run_data)

    def run_gridsearch_experiment(self):
        """Run the grid-search scenario and return collected artifacts for assertions."""
        reproducibility = _set_reproducibility(seed=42)
        configs = [
            {"epochs": 2, "learning_rate": 0.01, "n_input_neurons": 1},
            {"epochs": 4, "learning_rate": 0.03, "n_input_neurons": 1},
            {"epochs": 6, "learning_rate": 0.08, "n_input_neurons": 2},
            {"epochs": 10, "learning_rate": 0.12, "n_input_neurons": 2},
            {"epochs": 14, "learning_rate": 0.20, "n_input_neurons": 2},
        ]

        with Flowcept(
            workflow_name="Perceptron GridSearch",
            workflow_subtype=ML_Types.WORKFLOW,
            workflow_args=reproducibility,
        ):
            x_train, y_train, x_val, y_val, dataset_id = get_dataset(120, 0.8)
            results = []
            for idx, cfg in enumerate(configs, 1):
                result = train_and_validate(
                    n_input_neurons=cfg["n_input_neurons"],
                    epochs=cfg["epochs"],
                    learning_rate=cfg["learning_rate"],
                    x_train=x_train,
                    y_train=y_train,
                    x_val=x_val,
                    y_val=y_val,
                    dataset_id=dataset_id,
                    checkpoint_check=2,
                    config_id=f"cfg_{idx}",
                    torch_only=True,
                )
                results.append({"config": cfg, "result": result})

            selected = select_best_model(Flowcept.current_workflow_id)

        return {
            "workflow_id": Flowcept.current_workflow_id,
            "tasks": Flowcept.db.get_tasks_from_current_workflow(),
            "configs": configs,
            "results": results,
            "selected": selected,
        }

    def assert_gridsearch_experiment(self, run_data):
        """Assert all grid-search expectations from captured run data."""
        self.assert_gridsearch_tasks(tasks=run_data["tasks"], configs=run_data["configs"])
        best_cfg, best_model_object_id = self.assert_gridsearch_results(
            results=run_data["results"],
            selected=run_data["selected"],
        )
        self.assert_gridsearch_best_model_inference(best_cfg=best_cfg, best_model_object_id=best_model_object_id)
        self.assert_provenance_reports(
            workflow_id=run_data["workflow_id"],
            workflow_title="Perceptron GridSearch",
            expect_aggregation_method=True,
            expected_activity_lines=[
                "- **get_dataset** (subtype=`dataprep`)",
                "- **train_and_validate** (`n=5`, subtype=`learning`)",
                "- **select_best_model** (subtype=`model_selection`)",
            ],
            expected_content_lines=[
                "`tags`: `best`",
            ],
        )

    def assert_provenance_reports(
        self,
        workflow_id,
        workflow_title,
        expect_aggregation_method,
        expected_activity_lines,
        expected_content_lines,
    ):
        """Generate and validate markdown/pdf provenance reports for a workflow."""
        card_md_path = f"./WORKFLOW_CARD_{workflow_id}.md"
        if os.path.exists(card_md_path):
            os.remove(card_md_path)
        md_stats = Flowcept.generate_report(
            report_type="workflow_card",
            format="markdown",
            output_path=card_md_path,
            workflow_id=workflow_id,
        )
        assert os.path.exists(card_md_path)
        assert md_stats["report_type"] == "workflow_card"
        assert md_stats["format"] == "markdown"
        with open(card_md_path, "r", encoding="utf-8") as f:
            card_text = f.read()
        assert f"# Workflow Card: {workflow_title}" in card_text
        assert workflow_title in card_text
        if expect_aggregation_method:
            assert "## Aggregation Method" in card_text
        else:
            assert "## Aggregation Method" not in card_text
        assert "## Object Artifacts Summary" in card_text
        for line in expected_activity_lines:
            assert line in card_text
        for line in expected_content_lines:
            assert line in card_text

        try:
            import matplotlib  # noqa: F401
            import reportlab  # noqa: F401
        except ModuleNotFoundError:
            return

        report_pdf_path = f"./PROVENANCE_REPORT_{workflow_id}.pdf"
        if os.path.exists(report_pdf_path):
            os.remove(report_pdf_path)
        pdf_stats = Flowcept.generate_report(
            report_type="provenance_report",
            format="pdf",
            output_path=report_pdf_path,
            workflow_id=workflow_id,
        )
        assert os.path.exists(report_pdf_path)
        assert pdf_stats["report_type"] == "provenance_report"
        assert pdf_stats["format"] == "pdf"


    def assert_model_metadata(self, reloaded_torch_model, torch_model_object_id):
        assert hasattr(reloaded_torch_model, "_flowcept_model_object")
        flowcept_model_object = reloaded_torch_model._flowcept_model_object
        assert flowcept_model_object["object_id"] == torch_model_object_id
        assert "data" not in flowcept_model_object
        assert flowcept_model_object["object_type"] == "ml_model"
        assert flowcept_model_object["task_id"] is not None
        assert flowcept_model_object["workflow_id"] is not None
        assert flowcept_model_object["custom_metadata"] is not None
        assert "model_profile" in flowcept_model_object["custom_metadata"]

    def assert_gridsearch_tasks(self, tasks, configs):
        """Validate task capture structure and config coverage for grid search runs."""
        assert tasks is not None
        learning_tasks = [t for t in tasks if t.get("activity_id") == "train_and_validate"]
        assert len(learning_tasks) == 5
        assert all(task.get("subtype") == ML_Types.LEARNING for task in learning_tasks)
        assert all(task.get("generated", {}).get("torch_model_object_id") is not None for task in learning_tasks)
        assert all("ml_model_object_id" not in task.get("generated", {}) for task in learning_tasks)
        model_selection_tasks = [t for t in tasks if t.get("activity_id") == "select_best_model"]
        assert len(model_selection_tasks) == 1
        assert model_selection_tasks[0].get("subtype") == ML_Types.MODEL_SELECTION

        for cfg in configs:
            matched = [
                t
                for t in learning_tasks
                if t.get("used", {}).get("epochs") == cfg["epochs"]
                and t.get("used", {}).get("learning_rate") == cfg["learning_rate"]
                and t.get("used", {}).get("n_input_neurons") == cfg["n_input_neurons"]
            ]
            assert matched

    def assert_gridsearch_results(self, results, selected):
        """Validate grid-search result quality and selected model consistency."""
        assert len(results) == 5
        best_losses = [r["result"]["best_val_loss"] for r in results if r["result"]["best_val_loss"] is not None]
        assert len(best_losses) == 5
        rounded_losses = {round(float(loss), 4) for loss in best_losses}
        assert len(rounded_losses) > 1

        best_entry = min(results, key=lambda item: item["result"]["best_val_loss"])
        best_cfg = best_entry["config"]
        best_model_object_id = best_entry["result"]["torch_model_object_id"]
        assert best_model_object_id is not None
        assert selected["selected_model_object_id"] == best_model_object_id
        assert abs(float(selected["selected_loss"]) - float(best_entry["result"]["best_val_loss"])) < 1e-9
        return best_cfg, best_model_object_id

    def assert_gridsearch_best_model_inference(self, best_cfg, best_model_object_id):
        """Reload best grid-search model and verify one-step inference shape."""
        reloaded_torch_model = SingleLayerPerceptron(input_size=best_cfg["n_input_neurons"])
        Flowcept.db.load_torch_model(reloaded_torch_model, best_model_object_id)
        sample = torch.randn(1, best_cfg["n_input_neurons"])
        assert_single_inference_shape(reloaded_torch_model, sample)
