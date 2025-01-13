from uuid import uuid4

import torch
from torch.utils.data import Subset, DataLoader
from torchvision import datasets, transforms
from torch import nn, optim
from torch.nn import functional as F, Conv2d, Dropout, MaxPool2d, ReLU, Linear, Softmax

from flowcept import (
    Flowcept,
)

import threading

from flowcept import flowcept_torch

thread_state = threading.local()


@flowcept_torch
class MyNet(nn.Module):
    def __init__(
        self,
        conv_in_outs=[[1, 10], [10, 20]],
        conv_kernel_sizes=[5, 5],
        conv_pool_sizes=[2, 2],
        fc_in_outs=[[320, 50], [50, 10]],
        softmax_dims=[-9999, 1],  # first value will be ignored
        parent_workflow_id=None,
        parent_task_id=None,
    ):
        super().__init__()
        print("parent workflow id", parent_workflow_id)
        self.parent_task_id = parent_task_id

        self.model_type = "CNN"
        # TODO: add if len conv_in_outs > 0
        self.conv_layers = nn.Sequential()
        for i in range(0, len(conv_in_outs)):
            self.conv_layers.append(
                Conv2d(
                    conv_in_outs[i][0],
                    conv_in_outs[i][1],
                    kernel_size=conv_kernel_sizes[i],
                )
            )
            if i > 0:
                self.conv_layers.append(Dropout())
            self.conv_layers.append(MaxPool2d(conv_pool_sizes[i]))
            self.conv_layers.append(ReLU())

        # TODO: add if len fc inouts>0
        self.fc_layers = nn.Sequential()
        for i in range(0, len(fc_in_outs)):
            self.fc_layers.append(Linear(fc_in_outs[i][0], fc_in_outs[i][1]))
            if i == 0:
                self.fc_layers.append(ReLU())
                self.fc_layers.append(Dropout())
            else:
                self.fc_layers.append(Softmax(dim=softmax_dims[i]))
        self.view_size = fc_in_outs[0][0]

    def forward(self, x):
        x = self.conv_layers(x)
        x = x.view(-1, self.view_size)
        x = self.fc_layers(x)
        return x


class ModelTrainer(object):
    @staticmethod
    def build_train_test_loader(batch_size=128, random_seed=0, debug=True, subset_size=10):
        torch.manual_seed(random_seed)

        # Load the full MNIST dataset
        train_dataset = datasets.MNIST(
            "mnist_data",
            train=True,
            download=True,
            transform=transforms.Compose([transforms.ToTensor()]),
        )
        test_dataset = datasets.MNIST(
            "mnist_data",
            train=False,
            transform=transforms.Compose([transforms.ToTensor()]),
        )

        if debug:
            # Create smaller subsets for debugging
            train_dataset = Subset(train_dataset, range(subset_size))
            test_dataset = Subset(test_dataset, range(subset_size))

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=False)
        test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

        return train_loader, test_loader

    @staticmethod
    def _train(model, device, train_loader, optimizer, epoch):
        model.train()
        for batch_idx, (data, target) in enumerate(train_loader):
            data, target = data.to(device), target.to(device)
            optimizer.zero_grad()
            output = model(data)
            loss = F.nll_loss(output.log(), target)
            loss.backward()
            optimizer.step()
            if batch_idx % 100 == 0:
                print(
                    "Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}".format(
                        epoch,
                        batch_idx * len(data),
                        len(train_loader.dataset),
                        100.0 * batch_idx / len(train_loader),
                        loss.item(),
                    )
                )

    @staticmethod
    def _test(model, device, test_loader):
        model.eval()
        test_loss = 0
        correct = 0
        with torch.no_grad():
            for data, target in test_loader:
                data, target = data.to(device), target.to(device)
                output = model(data)
                test_loss += F.nll_loss(output.log(), target).item()  # sum up batch loss
                pred = output.max(1, keepdim=True)[1]  # get the index of the max log-probability
                correct += pred.eq(target.view_as(pred)).sum().item()

        test_loss /= len(test_loader.dataset)
        return {
            "loss": test_loss,
            "accuracy": 100.0 * correct / len(test_loader.dataset),
        }

    # @model_explainer()
    @staticmethod
    def model_fit(
        conv_in_outs=[[1, 10], [10, 20]],
        conv_kernel_sizes=[5, 5],
        conv_pool_sizes=[2, 2],
        fc_in_outs=[[320, 50], [50, 10]],
        softmax_dims=[-9999, 1],
        max_epochs=2,
        workflow_id=None,
        random_seed=0,
    ):
        try:
            from distributed.worker import thread_state

            task_id = thread_state.key
        except:
            task_id = str(uuid4())

        torch.manual_seed(random_seed)

        print("Workflow id in model_fit", workflow_id)  # TODO :base-interceptor-refactor:
        #  We are calling the consumer api here (sometimes for the second time)
        #  because we are capturing at two levels: at the model.fit and at
        #  every layer. Can we do it better?
        train_loader, test_loader = ModelTrainer.build_train_test_loader()
        if torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")
        model = MyNet(
            conv_in_outs=conv_in_outs,
            conv_kernel_sizes=conv_kernel_sizes,
            conv_pool_sizes=conv_pool_sizes,
            fc_in_outs=fc_in_outs,
            softmax_dims=softmax_dims,
            parent_workflow_id=workflow_id,
        )
        model = model.to(device)
        optimizer = optim.SGD(model.parameters(), lr=0.01, momentum=0.5)
        test_info = {}
        print("Starting training....")
        for epoch in range(1, max_epochs + 1):
            ModelTrainer._train(model, device, train_loader, optimizer, epoch)
            test_info = ModelTrainer._test(model, device, test_loader)
        print("Finished training....")
        batch = next(iter(test_loader))
        test_data, _ = batch
        result = test_info.copy()

        best_obj_id = Flowcept.db.save_or_update_torch_model(model, task_id=task_id, workflow_id=workflow_id, custom_metadata=result)
        result.update(
            {
                "best_obj_id": best_obj_id,
                "test_data": test_data,
                "task_id": task_id,
                "random_seed": random_seed,
            }
        )
        return result

    @staticmethod
    def generate_hp_confs(hp_conf: dict):
        model_fit_confs = []
        for i in range(0, len(hp_conf["n_conv_layers"])):
            model_fit_conf = {}

            n_conv_layers = hp_conf["n_conv_layers"][i]
            incr = hp_conf["conv_incrs"][i]
            conv_in_outs = []
            for k in range(0, n_conv_layers):
                i0 = 1 if k == 0 else k * incr
                i1 = (k * incr) + incr
                conv_in_outs.append([i0, i1])
            last_cv_i1 = i1
            model_fit_conf["conv_in_outs"] = conv_in_outs
            model_fit_conf["conv_kernel_sizes"] = [1] * n_conv_layers
            model_fit_conf["conv_kernel_sizes"][-1] = (
                28  # 28 found after trials and errors. It has to do with the batch_size 128
            )
            model_fit_conf["conv_pool_sizes"] = [1] * n_conv_layers

            for j in range(0, len(hp_conf["n_fc_layers"])):
                n_fc_layers = hp_conf["n_fc_layers"][j]
                incr = hp_conf["fc_increments"][j]
                fc_in_outs = []
                for k in range(0, n_fc_layers):
                    i0 = last_cv_i1 if k == 0 else k * incr
                    i1 = (k * incr) + incr
                    fc_in_outs.append([i0, i1])

                new_model_fit_conf = model_fit_conf.copy()
                new_model_fit_conf["fc_in_outs"] = fc_in_outs
                new_model_fit_conf["softmax_dims"] = [None]
                new_model_fit_conf["softmax_dims"].extend(
                    [hp_conf["softmax_dims"][j]] * (n_fc_layers - 1)
                )

                for e in hp_conf["max_epochs"]:
                    new_model_fit_conf["max_epochs"] = e
                    model_fit_confs.append(new_model_fit_conf)

        return model_fit_confs
