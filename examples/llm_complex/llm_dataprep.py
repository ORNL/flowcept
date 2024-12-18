from time import time

import torch
import os

from torch.utils.data import Subset
from torchtext.data.utils import get_tokenizer
from torchtext.vocab import build_vocab_from_iterator
from datasets import load_dataset


# Define a function to yield tokens from the dataset
def yield_tokens(tokenizer, data_iter):
    for item in data_iter:
        if len(item["text"]):
            yield tokenizer(item["text"])


# Define a function to process the raw text and convert it to tensors
def data_process(tokenizer, vocab, raw_text_iter):
    data = [
        torch.tensor(
            [vocab[token] for token in tokenizer(item["text"])],
            dtype=torch.long,
        )
        for item in raw_text_iter
    ]
    return torch.cat(tuple(filter(lambda t: t.numel() > 0, data)))


def get_dataset_ref(campaign_id, train_data, val_data, test_data):
    dataset_ref = f"{campaign_id}_train_shape_{train_data.shape}_val_shape_{val_data.shape}_test_shape_{test_data.shape}"
    return dataset_ref

def get_wiki_text_dataset(data_dir):
    # Load the WikiText2 dataset
    t0 = time()
    train_data = torch.load(os.path.join(data_dir, "train_data.tensor"))
    val_data = torch.load(os.path.join(data_dir, "val_data.tensor"))
    test_data = torch.load(os.path.join(data_dir, "test_data.tensor"))
    t1 = time()
    t_disk_load = t1 - t0

    try:
        if torch.cuda.is_available():
            device = torch.device("gpu")
        elif torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")

        t2 = time()
        t_device_available = t2 - t1
        train_data = train_data.to(device)
        val_data = val_data.to(device)
        test_data = test_data.to(device)
        t_gpu_load = time() - t2
    except:
        raise Exception("Couldn't send data to device")

    print("Train data", train_data.shape)
    print("Validation data", val_data.shape)
    print("Test data", test_data.shape)
    return (
        train_data,
        val_data,
        test_data,
        t_disk_load,
        t_device_available,
        t_gpu_load,
    )

def save_workflow(ntokens, train_data, val_data, test_data, dataset_ref, subset_size=None, tokenizer_type=None, campaign_id=None):
    from flowcept import WorkflowObject, Flowcept
    config = {
        "subset_size": subset_size,
        "tokenizer_type": tokenizer_type
    }
    dataset_prep_wf = WorkflowObject()
    dataset_prep_wf.used = config
    dataset_prep_wf.campaign_id = campaign_id
    dataset_prep_wf.name = "generate_wikitext_dataset"

    dataset_prep_wf.generated = {
        "ntokens": ntokens,
        "dataset_ref": dataset_ref,
        "train_data_shape": list(train_data.shape),
        "val_data_shape": list(val_data.shape),
        "test_data_shape": list(test_data.shape),
    }
    Flowcept.db.insert_or_update_workflow(dataset_prep_wf)
    print(dataset_prep_wf)
    return dataset_prep_wf.workflow_id, dataset_ref


def dataprep_workflow(data_dir="input_data",
                      tokenizer_type="basic_english",  # spacy, moses, toktok, revtok, subword
                      subset_size=None,
                      campaign_id=None):

    os.makedirs(data_dir, exist_ok=True)

    print("Downloading dataset")
    dataset = load_dataset("wikitext", "wikitext-2-v1")
    print("Ok, now saving it into the current directory")
    dataset.save_to_disk(os.path.join(data_dir, "wikitext-2-v1.data"))

    test_dataset = dataset["test"]
    train_dataset = dataset["train"]
    validation_dataset = dataset["validation"]

    if subset_size is not None and subset_size > 0:
        test_dataset = Subset(test_dataset, range(subset_size))
        train_dataset = Subset(train_dataset, range(subset_size))
        validation_dataset = Subset(validation_dataset, range(subset_size))

    # Build the vocabulary from the training dataset
    tokenizer = get_tokenizer(tokenizer_type)
    vocab = build_vocab_from_iterator(yield_tokens(tokenizer, train_dataset))
    vocab.set_default_index(vocab["<unk>"])
    ntokens = len(vocab)

    # Process the train, validation, and test datasets
    train_data = data_process(tokenizer, vocab, train_dataset)
    val_data = data_process(tokenizer, vocab, validation_dataset)
    test_data = data_process(tokenizer, vocab, test_dataset)

    train_data_path = os.path.join(data_dir, "train_data.tensor")
    val_data_path = os.path.join(data_dir, "val_data.tensor")
    test_data_path = os.path.join(data_dir, "test_data.tensor")

    torch.save(train_data, train_data_path)
    torch.save(val_data, val_data_path)
    torch.save(test_data, test_data_path)

    print(f"Saved files in {data_dir}. Now running some asserts.")

    train_data_loaded = torch.load(train_data_path)
    val_data_loaded = torch.load(val_data_path)
    test_data_loaded = torch.load(test_data_path)

    assert all(train_data == train_data_loaded)
    assert all(val_data == val_data_loaded)
    assert all(test_data == test_data_loaded)

    dataset_ref = get_dataset_ref(campaign_id, train_data, val_data, test_data)
    wf_id = save_workflow(ntokens, train_data, val_data, test_data, dataset_ref, subset_size=subset_size, tokenizer_type=tokenizer_type, campaign_id=campaign_id)
    return wf_id, dataset_ref, ntokens

