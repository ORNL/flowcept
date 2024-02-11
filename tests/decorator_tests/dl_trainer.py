import torch
from torchvision import datasets, transforms
from torch import nn, optim
from torch.nn import functional as F

from flowcept import model_explainer, model_profiler


class TestNet(nn.Module):
    def __init__(
        self,
        conv_in_outs=[[1, 10], [10, 20]],
        conv_kernel_sizes=[5, 5],
        conv_pool_sizes=[2, 2],
        fc_in_outs=[[320, 50], [50, 10]],
        softmax_dims=[-9999, 1],  # first value will be ignored
    ):
        super(TestNet, self).__init__()

        # TODO: add if len conv_in_outs > 0
        self.conv_layers = nn.Sequential()
        for i in range(0, len(conv_in_outs)):
            self.conv_layers.append(
                nn.Conv2d(
                    conv_in_outs[i][0],
                    conv_in_outs[i][1],
                    kernel_size=conv_kernel_sizes[i],
                )
            )
            if i > 0:
                self.conv_layers.append(nn.Dropout())
            self.conv_layers.append(nn.MaxPool2d(conv_pool_sizes[i]))
            self.conv_layers.append(nn.ReLU())

        # self.conv_layers = nn.Sequential(
        #     nn.Conv2d(1, 10, kernel_size=5),
        #     nn.MaxPool2d(2),
        #     nn.ReLU(),

        #     nn.Conv2d(10, 20, kernel_size=5),
        #     nn.Dropout(),
        #     nn.MaxPool2d(2),
        #     nn.ReLU(),
        # )

        # TODO: add if len fc inouts>0
        self.fc_layers = nn.Sequential()
        for i in range(0, len(fc_in_outs)):
            self.fc_layers.append(
                nn.Linear(fc_in_outs[i][0], fc_in_outs[i][1])
            )
            if i == 0:
                self.fc_layers.append(nn.ReLU())
                self.fc_layers.append(nn.Dropout())
            else:
                self.fc_layers.append(nn.Softmax(dim=softmax_dims[i]))
        self.view_size = fc_in_outs[0][0]

        # self.fc_layers = nn.Sequential(
        #     nn.Linear(320, 50),
        #     nn.ReLU(),
        #     nn.Dropout(),
        #     nn.Linear(50, 10),
        #     nn.Softmax(dim=1)
        # )

    def forward(self, x):
        x = self.conv_layers(x)
        x = x.view(-1, self.view_size)
        x = self.fc_layers(x)
        return x


class ModelTrainer(object):
    @staticmethod
    def build_train_test_loader(batch_size=128):
        train_loader = torch.utils.data.DataLoader(
            datasets.MNIST(
                "mnist_data",
                train=True,
                download=True,
                transform=transforms.Compose([transforms.ToTensor()]),
            ),
            batch_size=batch_size,
            shuffle=True,
        )

        test_loader = torch.utils.data.DataLoader(
            datasets.MNIST(
                "mnist_data",
                train=False,
                transform=transforms.Compose([transforms.ToTensor()]),
            ),
            batch_size=batch_size,
            shuffle=True,
        )
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
                test_loss += F.nll_loss(
                    output.log(), target
                ).item()  # sum up batch loss
                pred = output.max(1, keepdim=True)[
                    1
                ]  # get the index of the max log-probability
                correct += pred.eq(target.view_as(pred)).sum().item()

        test_loss /= len(test_loader.dataset)
        return {
            "loss": test_loss,
            "accuracy": 100.0 * correct / len(test_loader.dataset),
        }

    @staticmethod
    @model_profiler()
    @model_explainer()
    def model_fit(
        conv_in_outs=[[1, 10], [10, 20]],
        conv_kernel_sizes=[5, 5],
        conv_pool_sizes=[2, 2],
        fc_in_outs=[[320, 50], [50, 10]],
        softmax_dims=[-9999, 1],
        max_epochs=2,
        workflow_id=None,
    ):
        train_loader, test_loader = ModelTrainer.build_train_test_loader()
        device = torch.device("cpu")
        model = TestNet(
            conv_in_outs=conv_in_outs,
            conv_kernel_sizes=conv_kernel_sizes,
            conv_pool_sizes=conv_pool_sizes,
            fc_in_outs=fc_in_outs,
            softmax_dims=softmax_dims,
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
        result.update({"model": model, "test_data": test_data})
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
            model_fit_conf["conv_kernel_sizes"][
                -1
            ] = 28  # 28 found after trials and errors. It has to do with the batch_size 128
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
