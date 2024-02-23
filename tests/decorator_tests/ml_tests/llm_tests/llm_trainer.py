# The code in this file is based on:
# https://blog.paperspace.com/build-a-language-model-using-pytorch/
import math
import torch
import torch.nn as nn
import torch.optim as optim
from torchtext.data.utils import get_tokenizer
from torchtext.vocab import build_vocab_from_iterator
from datasets import load_dataset

import flowcept
from flowcept import model_profiler, FlowceptConsumerAPI
from flowcept.instrumentation.decorators.flowcept_task import flowcept_task
from flowcept.instrumentation.decorators.flowcept_torch import (
    register_modules,
    register_module_as_workflow,
    torch_args_handler,
)

tokenizer = get_tokenizer("basic_english")


# Define a function to batchify the data
def batchify(data, bsz):
    nbatch = data.size(0) // bsz
    data = data.narrow(0, 0, nbatch * bsz)
    data = data.view(bsz, -1).t().contiguous()
    return data


# Define a function to yield tokens from the dataset
def yield_tokens(data_iter):
    for item in data_iter:
        if len(item["text"]):
            yield tokenizer(item["text"])


# Define a function to process the raw text and convert it to tensors
def data_process(vocab, raw_text_iter):
    data = [
        torch.tensor(
            [vocab[token] for token in tokenizer(item["text"])],
            dtype=torch.long,
        )
        for item in raw_text_iter
    ]
    return torch.cat(tuple(filter(lambda t: t.numel() > 0, data)))


def get_batch(source, i, bptt=35):
    seq_len = min(bptt, len(source) - 1 - i)
    data = source[i : i + seq_len]
    target = source[i + 1 : i + 1 + seq_len].view(-1)
    return data, target


def get_wiki_text():
    # Load the WikiText2 dataset
    dataset = load_dataset("wikitext", "wikitext-2-v1")
    test_dataset = dataset["test"]
    train_dataset = dataset["train"]
    validation_dataset = dataset["validation"]

    # Build the vocabulary from the training dataset
    vocab = build_vocab_from_iterator(yield_tokens(train_dataset))
    vocab.set_default_index(vocab["<unk>"])
    ntokens = len(vocab)

    # Process the train, validation, and test datasets
    train_data = data_process(vocab, train_dataset)
    val_data = data_process(vocab, validation_dataset)
    test_data = data_process(vocab, test_dataset)

    print("Train data", train_data.shape)
    print("Validation data", val_data.shape)
    print("Test data", test_data.shape)
    return ntokens, train_data, val_data, test_data


# Define the TransformerModel class
class TransformerModel(nn.Module):
    def __init__(
        self,
        ntoken,
        d_model,
        nhead,
        d_hid,
        nlayers,
        dropout=0.5,
        pos_encoding_max_len=5000,
        parent_workflow_id=None,
    ):
        super(TransformerModel, self).__init__()
        self.workflow_id = register_module_as_workflow(
            self, parent_workflow_id
        )
        (
            TransformerEncoderLayer,
            TransformerEncoder,
            Embedding,
            Linear,
        ) = register_modules(
            [
                nn.TransformerEncoderLayer,
                nn.TransformerEncoder,
                nn.Embedding,
                nn.Linear,
            ],
            workflow_id=self.workflow_id,
        )
        self.model_type = "Transformer"
        self.src_mask = None
        self.pos_encoder = PositionalEncoding(
            d_model,
            dropout,
            max_len=pos_encoding_max_len,
            workflow_id=self.workflow_id,
        )
        encoder_layers = TransformerEncoderLayer(
            d_model, nhead, d_hid, dropout
        )
        self.transformer_encoder = TransformerEncoder(encoder_layers, nlayers)
        self.encoder = Embedding(ntoken, d_model)
        self.d_model = d_model
        self.decoder = Linear(d_model, ntoken)

    ##Generate a mask for the input sequence
    def _generate_square_subsequent_mask(self, sz):
        mask = (torch.triu(torch.ones(sz, sz)) == 1).transpose(0, 1)
        ## Change all the zeros to negative infinity and all the ones to zeros as follows:
        mask = (
            mask.float()
            .masked_fill(mask == 0, float("-inf"))
            .masked_fill(mask == 1, float(0.0))
        )
        return mask

    @flowcept_task(args_handler=torch_args_handler)
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
    def __init__(self, d_model, dropout=0.1, max_len=5000, workflow_id=None):
        super(PositionalEncoding, self).__init__()
        self.workflow_id = workflow_id
        Dropout = register_modules(
            [
                nn.Dropout,
            ],
            workflow_id=self.workflow_id,
        )

        self.dropout = Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float()
            * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer("pe", pe)

    @flowcept_task(args_handler=torch_args_handler)
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
        output = model(
            data
        )  # Forward pass: compute the output of the model given the input data
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


@model_profiler()
def model_train(
    ntokens,
    train_data,
    val_data,
    test_data,
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
):
    # TODO save random seed: https://pytorch.org/docs/stable/notes/randomness.html

    # TODO :base-interceptor-refactor: Can we do it better?
    with FlowceptConsumerAPI(
        flowcept.instrumentation.decorators.instrumentation_interceptor
    ):
        train_data = batchify(train_data, batch_size)
        val_data = batchify(val_data, eval_batch_size)
        test_data = batchify(test_data, eval_batch_size)

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = TransformerModel(
            ntokens,
            emsize,
            nhead,
            nhid,
            nlayers,
            dropout,
            pos_encoding_max_len,
            parent_workflow_id=workflow_id,
        ).to(device)
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=lr)
        best_val_loss = float(
            "inf"
        )  # Initialize the best validation loss to infinity
        # best_m = None
        # Iterate through the epochs
        for epoch in range(1, epochs + 1):
            print(f"Starting training for epoch {epoch}/{epochs}")
            # Train the model on the training data and calculate the training loss
            train_loss = train_epoch(
                ntokens, model, train_data, criterion, optimizer, batch_size
            )

            # Evaluate the model on the validation data and calculate the validation loss
            val_loss = evaluate(
                ntokens, model, val_data, criterion, eval_batch_size
            )

            # Print the training and validation losses for the current epoch
            print(
                f"Epoch: {epoch}, Train loss: {train_loss:.2f}, Validation loss: {val_loss:.2f}"
            )

            # If the validation loss has improved, save the model's state
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                # best_m = model
                torch.save(model.state_dict(), "../transformer_wikitext2.pth")

        print("Finished training")
        # Load the best model's state
        best_m = TransformerModel(
            ntokens, emsize, nhead, nhid, nlayers, dropout
        ).to(device)
        print("Loading model")
        torch_loaded = torch.load("../transformer_wikitext2.pth")
        best_m.load_state_dict(torch_loaded)

        print("Evaluating")
        # Evaluate the best model on the test dataset
        test_loss = evaluate(
            ntokens, best_m, test_data, criterion, eval_batch_size
        )
        print(f"Test loss: {test_loss:.2f}")

        return {
            "test_loss": test_loss,
            "train_loss": train_loss,
            "val_loss": val_loss,
            "model": model,
        }


# Set the batch sizes and batchify the data
# batch_size = 20
# eval_batch_size = 10
#
# emsize = 200  # 200 embedding dimension
# nhid = 200  # 200 dimension of the feedforward network model in ``nn.TransformerEncoder``
# nlayers = 2  # number of ``nn.TransformerEncoderLayer`` in ``nn.TransformerEncoder`
# nhead = 2  # number of heads in ``nn.MultiheadAttention``
# dropout = 0.2  # dropout probability
# epochs = 1  # Set the number of epochs for training
# # lr=0.001
# lr = 0.5
# pos_encoding_max_len=500 #5000
