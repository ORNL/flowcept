# The code in this file is based on:
# https://blog.paperspace.com/build-a-language-model-using-pytorch/
import math
from time import time, sleep

import torch
import torch.nn as nn
import torch.optim as optim
from torch.nn import Embedding, Linear, TransformerEncoder, TransformerEncoderLayer, Dropout

from flowcept.flowceptor.adapters.dask.dask_plugins import get_flowcept_task
from llm_dataprep import get_wiki_text_dataset
from flowcept import Flowcept, flowcept_torch
from flowcept.instrumentation.flowcept_torch import FlowceptEpochLoop, FlowceptBatchLoop


def get_batch(source, i, bptt=35):
    seq_len = min(bptt, len(source) - 1 - i)
    data = source[i : i + seq_len]
    target = source[i + 1 : i + 1 + seq_len].view(-1)
    return data, target


@flowcept_torch
class TransformerModel(nn.Module):

    def __init__(
        self,
        ntokens,
        emsize,
        nhead,
        nhid,
        nlayers,
        dropout=0.5,
        pos_encoding_max_len=5000,
        parent_task_id=None,   # All these arguments seem unused but are used in the wrapper.
        campaign_id=None,
        parent_workflow_id=None,
        custom_metadata: dict = None,
        get_profile: bool = False,
        save_workflow: bool = True,
        inspect_children_tensors: bool = True,
        capture_enabled=True,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.model_type = "Transformer"
        self.src_mask = None
        self.pos_encoder = PositionalEncoding(
            emsize,
            dropout,
            max_len=pos_encoding_max_len,
        )
        encoder_layers = TransformerEncoderLayer(emsize, nhead, nhid, dropout)
        self.transformer_encoder = TransformerEncoder(encoder_layers, nlayers)
        self.encoder = Embedding(ntokens, emsize)
        self.decoder = Linear(emsize, ntokens)
        self.d_model = emsize

    # ##Generate a mask for the input sequence
    def _generate_square_subsequent_mask(self, sz):
        mask = (torch.triu(torch.ones(sz, sz)) == 1).transpose(0, 1)
        ## Change all the zeros to negative infinity and all the ones to zeros as follows:
        mask = mask.float().masked_fill(mask == 0, float("-inf")).masked_fill(mask == 1, float(0.0))
        return mask

    def forward(self, src, *args, **kwargs):
        if self.src_mask is None or self.src_mask.size(0) != len(src):
            device = src.device
            mask = self._generate_square_subsequent_mask(len(src)).to(device)
            self.src_mask = mask

        src = self.encoder(src) * math.sqrt(self.d_model)
        src = self.pos_encoder(src)
        output = self.transformer_encoder(src, self.src_mask)
        output = self.decoder(output)
        return output

# Define the PositionalEncoding class
class PositionalEncoding(nn.Module):
    def __init__(
        self,
        emsize,
        dropout=0.1,
        max_len=5000,
    ):
        super(PositionalEncoding, self).__init__()
        self.dropout = Dropout(p=dropout)

        pe = torch.zeros(max_len, emsize)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, emsize, 2).float() * (-math.log(10000.0) / emsize))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer("pe", pe)

    def forward(self, x):
        x = x + self.pe[: x.size(0), :]
        return self.dropout(x)

def train_epoch(ntokens, model, train_data, criterion, optimizer, bptt=35, epochs_loop=None, with_flowcept=True):
    model.train()  # Set the model to training mode
    total_loss = 0.0  # Initialize the total loss to 0

    # Iterate through the mini-batches of data
    loop = FlowceptBatchLoop(items=enumerate(range(0, train_data.size(0) - 1, bptt)),
                             epochs_loop=epochs_loop,
                             items_length=math.ceil((train_data.size(0) - 1) / bptt),
                             capture_enabled=with_flowcept)
    for batch, i in loop:
        data, targets = get_batch(
            train_data, i, bptt
        )  # Get the input data and targets for the current mini-batch
        optimizer.zero_grad()  # Reset the gradients to zero before the next backward pass
        output = model(data)  # Forward pass: compute the output of the model given the input data
        loss = criterion(
            output.view(-1, ntokens), targets
        )  # Calculate the loss between the model output and the targets
        loss.backward()  # Backward pass: compute the gradients of the loss with respect to the model parameters
        optimizer.step()  # Update the model parameters using the computed gradients
        loss_item = loss.item()
        total_loss += loss_item  # Accumulate the total loss
        loop.end_iter({"loss": loss_item})
    return total_loss / (batch + 1)  # Return the average loss per mini-batch


def evaluate(ntokens, model, data_source, criterion, bptt=35, epochs_loop=None, with_flowcept=True):
    model.eval()  # Set the model to evaluation mode
    total_loss = 0.0  # Initialize the total loss to 0

    # Use torch.no_grad() to disable gradient calculation during evaluation
    with torch.no_grad():
        loop = FlowceptBatchLoop(items=enumerate(range(0, data_source.size(0) - 1, bptt)),
                                 epochs_loop=epochs_loop,
                                 step="eval",
                                 items_length=math.ceil((data_source.size(0) - 1) / bptt),
                                 capture_enabled=with_flowcept)
        # Iterate through the mini-batches of data
        for batch, i in loop:
            data, targets = get_batch(
                data_source, i, bptt
            )  # Get the input data and targets for the current mini-batch
            output = model(
                data
            )  # Forward pass: compute the output of the model given the input data
            loss = criterion(
                output.view(-1, ntokens), targets
            )  # Calculate the loss between the model output and the targets
            loss_item = loss.item()
            total_loss += loss_item  # Accumulate the total loss
            loop.end_iter({"loss": loss_item})

    return total_loss / (i + 1)  # Return the average loss per mini-batch


def model_train(
    ntokens,
    train_data_path,
    val_data_path,
    test_data_path,
    batch_size,
    eval_batch_size,
    epochs,
    emsize,
    nhead,
    nhid,
    nlayers,
    dropout,
    lr,
    pos_encoding_max_len,
    random_seed=0,
    workflow_id=None,
    campaign_id=None,
    with_persistence=True,
    with_flowcept=True,
    dask_map_gpus=False,
    *args,
    **kwargs
):
    print("Starting model_train!")
    try:
        if with_flowcept:
            main_task_id = get_flowcept_task().task_id
        else:
            main_task_id = None
    except:
        main_task_id = None
    torch.manual_seed(random_seed)

    print("Starting to get data!")
    train_data, val_data, test_data, t_disk_load, t_device_available, t_gpu_load, device = get_wiki_text_dataset(train_data_path, val_data_path, test_data_path,dask_map_gpus=dask_map_gpus)
    print("Got data!")
    model = TransformerModel(
        ntokens,
        emsize,
        nhead,
        nhid,
        nlayers,
        dropout,
        pos_encoding_max_len,
        parent_workflow_id=workflow_id,
        campaign_id=campaign_id,
        get_profile=True,
        capture_enabled=with_flowcept
    ).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)
    best_val_loss = float("inf")  # Initialize the best validation loss to infinity
    best_obj_id = None  # Initialize with unknown best model
    # Iterate through the epochs
    epochs_loop = FlowceptEpochLoop(range(1, epochs + 1), parent_task_id=main_task_id, model=model, capture_enabled=with_flowcept)
    t0 = time()
    val_loss = -1
    train_loss = -1
    for epoch in epochs_loop:
        print(f"Starting training for epoch {epoch}/{epochs}")
        # Train the model on the training data and calculate the training loss
        train_loss = train_epoch(ntokens, model, train_data, criterion, optimizer, batch_size, epochs_loop=epochs_loop)
        print(f"... train loss: {train_loss}. Starting val...")
        # Evaluate the model on the validation data and calculate the validation loss
        val_loss = evaluate(ntokens, model, val_data, criterion, eval_batch_size, epochs_loop=epochs_loop)
        print(f"... val loss: {val_loss}.")
        # Print the training and validation losses for the current epoch
        print(f"Epoch: {epoch}, Train loss: {train_loss:.2f}, Validation loss: {val_loss:.2f}") # TODO revisit loop because var epoch here is none?

        # If the validation loss has improved, save the model's state
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            if with_persistence:
                best_obj_id = Flowcept.db.save_or_update_torch_model(
                    model,
                    object_id=best_obj_id,
                    task_id=epochs_loop.get_current_iteration_id(),
                    workflow_id=workflow_id,
                    custom_metadata={"best_val_loss": best_val_loss}
                )

        epochs_loop.end_iter({"train_loss": train_loss, "val_loss": val_loss})

    t1 = time()
    print("Finished training")

    sleep(3) # Adding some sleep time to help processing calm down a bit.

    test_loss = -1
    if with_persistence:
        # Load the best model's state
        best_m = TransformerModel(
            ntokens,
            emsize,
            nhead,
            nhid,
            nlayers,
            dropout,
            parent_workflow_id=workflow_id,
            campaign_id=campaign_id,
            parent_task_id=main_task_id,
            capture_enabled=False
        ).to(device)
        print("Loading model")
        Flowcept.db.load_torch_model(best_m, best_obj_id)
        print("Evaluating")
        # Evaluate the best model on the test dataset
        test_loss = evaluate(ntokens, best_m, test_data, criterion, eval_batch_size)

    return {
        "test_loss": test_loss,
        "train_loss": train_loss,
        "val_loss": val_loss,
        "training_time": t1 - t0,
        "best_obj_id": best_obj_id,
        "t_disk_load": t_disk_load,
        "t_device_available": t_device_available,
        "t_gpu_load": t_gpu_load,
        "device": str(device)
    }