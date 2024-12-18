# The code in this file is based on:
# https://blog.paperspace.com/build-a-language-model-using-pytorch/
import math
import os
from time import time

import torch
import torch.nn as nn
import torch.optim as optim
from torch.nn import Embedding, Linear, TransformerEncoder, TransformerEncoderLayer, Dropout
from torch.utils.data import Subset
from torchtext.data.utils import get_tokenizer
from torchtext.vocab import build_vocab_from_iterator
from datasets import load_dataset

from examples.llm_complex.llm_dataprep import get_wiki_text_dataset
from flowcept import Flowcept, FlowceptLoop, flowcept_torch
from flowcept.configs import N_GPUS


# Define a function to batchify the data
def batchify(data, bsz):
    nbatch = data.size(0) // bsz
    data = data.narrow(0, 0, nbatch * bsz)
    data = data.view(bsz, -1).t().contiguous()
    return data


# # Define a function to yield tokens from the dataset
# def yield_tokens(tokenizer, data_iter):
#     for item in data_iter:
#         if len(item["text"]):
#             yield tokenizer(item["text"])
#
#
# # Define a function to process the raw text and convert it to tensors
# def data_process(tokenizer, vocab, raw_text_iter):
#     data = [
#         torch.tensor(
#             [vocab[token] for token in tokenizer(item["text"])],
#             dtype=torch.long,
#         )
#         for item in raw_text_iter
#     ]
#     return torch.cat(tuple(filter(lambda t: t.numel() > 0, data)))


def get_batch(source, i, bptt=35):
    seq_len = min(bptt, len(source) - 1 - i)
    data = source[i : i + seq_len]
    target = source[i + 1 : i + 1 + seq_len].view(-1)
    return data, target


# def get_wiki_text(
#     tokenizer_type="basic_english", # spacy, moses, toktok, revtok, subword
#     subset_size=None
# ):
#     # Load the WikiText2 dataset
#     dataset = load_dataset("wikitext", "wikitext-2-v1")
#     test_dataset = dataset["test"]
#     train_dataset = dataset["train"]
#     validation_dataset = dataset["validation"]
#
#     if subset_size is not None and subset_size > 0:
#         test_dataset = Subset(test_dataset, range(subset_size))
#         train_dataset = Subset(train_dataset, range(subset_size))
#         validation_dataset = Subset(validation_dataset, range(subset_size))
#
#     # Build the vocabulary from the training dataset
#     tokenizer = get_tokenizer(tokenizer_type)
#     vocab = build_vocab_from_iterator(yield_tokens(tokenizer, train_dataset))
#     vocab.set_default_index(vocab["<unk>"])
#     ntokens = len(vocab)
#
#     # Process the train, validation, and test datasets
#     train_data = data_process(tokenizer, vocab, train_dataset)
#     val_data = data_process(tokenizer, vocab, validation_dataset)
#     test_data = data_process(tokenizer, vocab, test_dataset)
#
#     device = torch.device("cpu")
#     if torch.cuda.is_available():
#         device = torch.device("gpu")
#     elif torch.backends.mps.is_available():
#         device = torch.device("mps")
#
#     if device.type != 'cpu':
#         train_data = train_data.to(device)
#         val_data = val_data.to(device)
#         test_data = test_data.to(device)
#
#     print("Train data", train_data.shape)
#     print("Validation data", val_data.shape)
#     print("Test data", test_data.shape)
#     return ntokens, train_data, val_data, test_data


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

    def forward(self, src):
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

def train_epoch(ntokens, model, train_data, criterion, optimizer, bptt=35):
    model.train()  # Set the model to training mode
    total_loss = 0.0  # Initialize the total loss to 0

    # Iterate through the mini-batches of data
    for batch, i in enumerate(range(0, train_data.size(0) - 1, bptt)):
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
        total_loss += loss.item()  # Accumulate the total loss

    return total_loss / (batch + 1)  # Return the average loss per mini-batch


def evaluate(ntokens, model, data_source, criterion, bptt=35):
    model.eval()  # Set the model to evaluation mode
    total_loss = 0.0  # Initialize the total loss to 0

    # Use torch.no_grad() to disable gradient calculation during evaluation
    with torch.no_grad():
        # Iterate through the mini-batches of data
        for i in range(0, data_source.size(0) - 1, bptt):
            data, targets = get_batch(
                data_source, i, bptt
            )  # Get the input data and targets for the current mini-batch
            output = model(
                data
            )  # Forward pass: compute the output of the model given the input data
            loss = criterion(
                output.view(-1, ntokens), targets
            )  # Calculate the loss between the model output and the targets
            total_loss += loss.item()  # Accumulate the total loss

    return total_loss / (i + 1)  # Return the average loss per mini-batch




def model_train(
    ntokens,
    input_data_dir,
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
    workflow_id=None,
    campaign_id=None,
    *args,
    **kwargs
):
    try:
        from distributed.worker import thread_state
        main_task_id = thread_state.key if hasattr(thread_state, "key") else None
    except:
        main_task_id = None
    torch.manual_seed(0)  # TODO: parametrize and save it

    train_data, val_data, test_data, t_disk_load, t_device_available, t_gpu_load = get_wiki_text_dataset(input_data_dir)

    train_data = batchify(train_data, batch_size)
    val_data = batchify(val_data, eval_batch_size)
    test_data = batchify(test_data, eval_batch_size)

    if torch.cuda.is_available():
        device = torch.device("gpu")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

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
        custom_metadata={"model_step": "train", "cuda_visible": N_GPUS},
    ).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)
    best_val_loss = float("inf")  # Initialize the best validation loss to infinity
    # Iterate through the epochs
    t0 = time()

    epochs_loop = FlowceptLoop(range(1, epochs + 1), "epochs_loop", "epoch", parent_task_id=main_task_id)
    for epoch in epochs_loop:
        print(f"Starting training for epoch {epoch}/{epochs}")
        # Train the model on the training data and calculate the training loss
        model.set_parent_task_id(epochs_loop.current_iteration_task.get("task_id", None))
        train_loss = train_epoch(ntokens, model, train_data, criterion, optimizer, batch_size)

        # Evaluate the model on the validation data and calculate the validation loss
        val_loss = evaluate(ntokens, model, val_data, criterion, eval_batch_size)

        # Print the training and validation losses for the current epoch
        print(f"Epoch: {epoch}, Train loss: {train_loss:.2f}, Validation loss: {val_loss:.2f}") # TODO revisit loop because var epoch here is none?

        # If the validation loss has improved, save the model's state
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_obj_id = Flowcept.db.save_torch_model(
                model,
                task_id=epochs_loop.current_iteration_task.get("task_id", None),
                workflow_id=workflow_id,
                custom_metadata={"best_val_loss": best_val_loss}
            )

        epochs_loop.end_iter({"train_loss": train_loss, "val_loss": val_loss})

    print("Finished training")
    t1 = time()

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
        custom_metadata={
            "model_step": "test",
            "cuda_visible": N_GPUS,
        },
        parent_task_id=main_task_id
    ).to(device)
    print("Loading model")
    Flowcept.db.load_torch_model(best_m, best_obj_id)
    print("Evaluating")
    # Evaluate the best model on the test dataset
    test_loss = evaluate(ntokens, best_m, test_data, criterion, eval_batch_size)
    print(f"Test loss: {test_loss:.2f}")
    return {
        "test_loss": test_loss,
        "train_loss": train_loss,
        "val_loss": val_loss,
        "training_time": t1 - t0,
        "best_obj_id": best_obj_id
    }
