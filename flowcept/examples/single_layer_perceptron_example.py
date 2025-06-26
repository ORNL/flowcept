import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim

from flowcept import Flowcept
from flowcept.instrumentation.flowcept_task import flowcept_task
from flowcept.instrumentation.flowcept_torch import flowcept_torch


@flowcept_torch
class SingleLayerPerceptron(nn.Module):
    def __init__(self, input_size, **kwargs):
        super().__init__()
        # super(SingleLayerPerceptron, self).__init__() # TODO
        self.layer = nn.Linear(input_size, 1)

    def forward(self, x):
        return torch.sigmoid(self.layer(x))  # Sigmoid for binary classification


def get_dataset(n_samples, split_ratio):
    """
    Generate a simple binary classification dataset
    """
    X = torch.cat(
        [torch.randn(n_samples // 2, 2) + 2, torch.randn(n_samples // 2, 2) - 2])
    y = torch.cat([torch.zeros(n_samples // 2), torch.ones(n_samples // 2)]).unsqueeze(
        1)  # Labels: 0 and 1

    # Split the dataset into training and validation sets
    n_train = int(n_samples * split_ratio)
    X_train, X_val = X[:n_train], X[n_train:]
    y_train, y_val = y[:n_train], y[n_train:]
    return X_train, y_train, X_val, y_val


def train_and_validate(n_input_neurons, epochs, X_train, y_train, X_val, y_val):
    # Initialize model, loss function, and optimizer
    model = SingleLayerPerceptron(input_size=n_input_neurons, get_profile=True)
    criterion = nn.BCELoss()  # Binary Cross-Entropy Loss
    optimizer = optim.SGD(model.parameters(), lr=0.1)

    for epoch in range(epochs):
        model.train()
        outputs = model(X_train)
        loss = criterion(outputs, y_train)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        val_loss, val_accuracy = validate(model, criterion, X_val, y_val)
        print(f"Epoch [{epoch + 1}/{epochs}], "
              f"Train Loss: {loss.item():.4f}, "
              f"Val Loss: {val_loss:.4f}, "
              f"Val Accuracy: {val_accuracy:.2f}")

    # Final evaluation on the validation set
    final_val_loss, final_val_accuracy = validate(model, criterion, X_val, y_val)
    print(f"\nFinal Validation Loss: {final_val_loss:.4f}, "
          f"Final Validation Accuracy: {final_val_accuracy:.2f}")
    return {
        "val_loss": final_val_loss,
        "val_accuracy": final_val_accuracy
    }


def validate(model, criterion, X_val, y_val):
    model.eval()  # Set model to evaluation mode
    with torch.no_grad():
        outputs = model(X_val)
        loss = criterion(outputs, y_val)
        predictions = outputs.round()
        accuracy = (predictions.eq(y_val).sum().item()) / y_val.size(0)
    return loss.item(), accuracy


@flowcept_task
def main(n_samples, split_ratio, n_input_neurons, epochs, seed):
    torch.manual_seed(seed)
    X_train, y_train, X_val, y_val = get_dataset(n_samples, split_ratio)
    return train_and_validate(n_input_neurons, epochs, X_train, y_train, X_val, y_val)


if __name__ == "__main__":

    params = dict(
        n_samples=200,
        split_ratio=0.8,
        n_input_neurons=2,
        epochs=10,
        seed=0
    )

    with Flowcept(workflow_name="perceptron_train", workflow_args=params):
        result = main(**params)
        print(result)

    # Querying stored data
    workflows = Flowcept.db.query({"campaign_id": Flowcept.campaign_id}, collection="workflows")
    train_wf = module_forward_wf = None
    for wf in workflows:
        if wf["name"] == "perceptron_train":
            train_wf = wf
        elif wf["name"] == "SingleLayerPerceptron":
            module_forward_wf = wf

    # print(train_wf)
    train_wf_task = Flowcept.db.query({"workflow_id": train_wf["workflow_id"]})
    print(train_wf_task)
    # print(module_forward_wf)

    module_tasks = Flowcept.db.query({"workflow_id": module_forward_wf["workflow_id"]})
    module_tasks_df = pd.DataFrame(module_tasks)
    assert len(module_tasks_df) > 0
