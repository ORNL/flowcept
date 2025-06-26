import json
from time import time, ctime

import torch
import os

from torch.utils.data import Subset
from torchtext.data.utils import get_tokenizer
from torchtext.vocab import build_vocab_from_iterator
from datasets import load_dataset, load_from_disk

from flowcept.commons.utils import replace_non_serializable

def batchify(data, bsz):
    nbatch = data.size(0) // bsz
    data = data.narrow(0, 0, nbatch * bsz)
    data = data.view(bsz, -1).t().contiguous()
    return data


# Define a function to yield tokens from the dataset
def yield_tokens(tokenizer, data_iter):
    for item in data_iter:
        if len(item["text"]):
            yield tokenizer(item["text"])


# Define a function to process the raw text and convert it to tensors
def data_process_old(tokenizer, vocab, raw_text_iter):
    i = 0
    data = []
    for item in raw_text_iter:
        tokens = tokenizer(item["text"])
        indices = []
        for token in tokens:
            indices.append(vocab[token])
        tensor = torch.tensor(indices, dtype=torch.long)
        data.append(tensor)
        i += 1
    tensor_return = torch.cat(tuple(filter(lambda t: t.numel() > 0, data)))
    return tensor_return


def data_process(tokenizer, vocab, raw_text_iter):
    data = []
    mapping = []  # To store the index of the raw dataset for each processed tensor
    for idx, item in enumerate(raw_text_iter):
        tokens = tokenizer(item["text"])
        indices = [vocab[token] for token in tokens]
        tensor = torch.tensor(indices, dtype=torch.long)
        if tensor.numel() > 0:
            data.append(tensor)
            mapping.extend([idx] * len(tensor))  # Map each token to its raw text index
    tensor_return = torch.cat(data)
    return tensor_return, mapping

def dask_map_gpus_to_worker():
    from dask.distributed import get_worker,get_client

    d = get_client().scheduler_info()['workers']
    w_name = get_worker().name
    node = w_name.replace("tcp://","").split(":")[0]
    workers = list(d.keys())
    buckets = {}
    for worker in workers:
        target = worker.replace("tcp://","").split(":")[0]
        if target in buckets.keys():
            buckets[target].append(worker)
        else:
            buckets[target] = [worker]

    for key in buckets.keys():
        buckets[key] = sorted(buckets[key])
    gpu_id = buckets[node].index(w_name)
    print(f"Name-rank: {w_name}-{gpu_id}",flush=True)
    return gpu_id


def get_wiki_text_dataset(train_data_path, val_data_path, test_data_path, dask_map_gpus=False):
    # Load the WikiText2 dataset
    t0 = time()
    train_data = torch.load(train_data_path)
    val_data = torch.load(val_data_path)
    test_data = torch.load(test_data_path)
    t1 = time()
    t_disk_load = t1 - t0

    try:
        if torch.cuda.is_available():
            if dask_map_gpus:
                gpu_id = dask_map_gpus_to_worker()
            else:
                gpu_id = 0
            device = torch.device(f"cuda:{gpu_id}")
            torch.cuda.set_device(device)

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

    return (
        train_data,
        val_data,
        test_data,
        t_disk_load,
        t_device_available,
        t_gpu_load,
        device
    )


def get_dataset_ref(dataset):
    return id(dataset)


def save_workflow(campaign_id, used, generated, with_persistence=True):
    from flowcept import WorkflowObject, Flowcept
    dataset_prep_wf = WorkflowObject()
    dataset_prep_wf.used = used
    dataset_prep_wf.campaign_id = campaign_id
    dataset_prep_wf.name = "DataPrepWorkflow"
    dataset_prep_wf.generated = generated
    if with_persistence:
        Flowcept.db.insert_or_update_workflow(dataset_prep_wf)
    return dataset_prep_wf.workflow_id


def get_raw_batch(raw_dataset, mapping, i, batch_size):
    start_idx = i
    end_idx = i + batch_size
    raw_indices = mapping[start_idx:end_idx]  # Indices of raw items in this batch
    raw_batch = [raw_dataset[idx]["text"] for idx in set(raw_indices)]  # Unique raw items
    return raw_batch




def dataprep_workflow(data_dir="input_data",
                      tokenizer_type="basic_english",  # spacy, moses, toktok, revtok, subword
                      batch_size=20,
                      eval_batch_size=10,
                      subset_size=None,
                      campaign_id=None,
                      with_persistence=True
                      ):

    dataset_characteristics = f'batch_size_{batch_size}_eval_batch_size_{eval_batch_size}_subset_size_{subset_size}_tokenizer_{tokenizer_type}'
    base_path = os.path.realpath(os.path.join(data_dir, dataset_characteristics))

    train_data_path = f"{base_path}_train_data.tensor"
    val_data_path = f"{base_path}_val_data.tensor"
    test_data_path = f"{base_path}_test_data.tensor"
    val_data_mapping_path = f"{base_path}_val_data_mapping.tensor"
    dataset_info_path = f"{base_path}_dataset_info.json"
    n_batches_path = f"{base_path}_n_batches.json"
    n_tokens_path = f"{base_path}_n_tokens.txt"

    if not os.path.exists(train_data_path):

        download_files(
            batch_size, data_dir, eval_batch_size, subset_size, test_data_path, tokenizer_type, train_data_path,
            val_data_mapping_path, val_data_path, dataset_info_path, n_batches_path, n_tokens_path)
    else:
        print(f"Input files {base_path}* were found! We are not going to re-download or re-generate anything.")

    train_data = torch.load(train_data_path)
    val_data = torch.load(val_data_path)
    test_data = torch.load(test_data_path)

    with open(n_batches_path) as f:
        n_batches = json.load(f)
    with open(dataset_info_path) as f:
        dataset_info = json.load(f)
    with open(n_tokens_path) as f:
        ntokens = int(f.read())
    #
    # assert torch.equal(train_data, train_data_loaded), "Train data mismatch"
    # assert torch.equal(val_data, val_data_loaded), "Validation data mismatch"
    # assert torch.equal(test_data, test_data_loaded), "Test data mismatch"

    used = {
        "train_batch_size": batch_size,
        "val_batch_size": eval_batch_size,
        "test_batch_size": eval_batch_size,
        "subset_size": subset_size,
        "tokenizer_type": tokenizer_type,
    }
    generated = {
        "dataset_info": dataset_info,
        "ntokens": ntokens,
        "dataset_ref": dataset_info["dataset_ref"],
        "train_data_shape": list(train_data.shape),
        "val_data_shape": list(val_data.shape),
        "test_data_shape": list(test_data.shape),
        "train_data_path": train_data_path,
        "test_data_path": test_data_path,
        "val_data_path": val_data_path,
    }
    generated.update(n_batches)
    wf_id = save_workflow(campaign_id, used, generated, with_persistence)
    return wf_id, generated


def download_files(batch_size, data_dir, eval_batch_size, subset_size, test_data_path, tokenizer_type, train_data_path,
                   val_data_mapping_path, val_data_path, dataset_info_path, n_batches_path, n_tokens_path):
    os.makedirs(data_dir, exist_ok=True)
    dataset_path = os.path.join(data_dir, "wikitext-2-v1.data")
    if os.path.exists(dataset_path):
        dataset = load_from_disk(dataset_path)
    else:
        print("Downloading dataset")
        dataset = load_dataset("wikitext", "wikitext-2-v1")
        print(f"Ok, now saving it into {dataset_path}")
        dataset.save_to_disk(dataset_path)
    test_dataset = dataset["test"]
    train_dataset = dataset["train"]
    validation_dataset = dataset["validation"]
    dataset_info = {
        "train": replace_non_serializable(train_dataset.info.__dict__),
        "val": replace_non_serializable(validation_dataset.info.__dict__),
        "test": replace_non_serializable(test_dataset.info.__dict__),
        "dataset_ref": get_dataset_ref(dataset),
        "dataset_local_file_download_time": ctime(os.stat(dataset_path).st_ctime)
    }
    with open(dataset_info_path, "w") as file:
        json.dump(dataset_info, file, indent=2)

    if subset_size is not None and subset_size > 0:
        test_dataset = Subset(test_dataset, range(subset_size))
        train_dataset = Subset(train_dataset, range(subset_size))
        validation_dataset = Subset(validation_dataset, range(subset_size))
    # Build the vocabulary from the training dataset
    tokenizer = get_tokenizer(tokenizer_type)
    vocab = build_vocab_from_iterator(yield_tokens(tokenizer, train_dataset))
    vocab.set_default_index(vocab["<unk>"])
    ntokens = len(vocab)
    with open(n_tokens_path, 'w') as f:
        f.write(str(ntokens))
    # Process the train, validation, and test datasets
    train_data, train_data_mapping = data_process(tokenizer, vocab, train_dataset)
    val_data, val_data_mapping = data_process(tokenizer, vocab, validation_dataset)
    test_data, test_data_mapping = data_process(tokenizer, vocab, test_dataset)
    train_data = batchify(train_data, batch_size)
    val_data = batchify(val_data, eval_batch_size)
    test_data = batchify(test_data, eval_batch_size)
    train_n_batches = len(list(enumerate(range(0, train_data.size(0) - 1, batch_size))))
    val_n_batches = len(list(enumerate(range(0, val_data.size(0) - 1, eval_batch_size))))
    test_n_batches = val_n_batches
    with open(n_batches_path, "w") as file:
        json.dump({"train_n_batches": train_n_batches, "val_n_batches":val_n_batches, "test_n_batches": test_n_batches}, file, indent=2)
    torch.save(train_data, train_data_path)
    torch.save(val_data, val_data_path)
    torch.save(test_data, test_data_path)
    torch.save(val_data_mapping, val_data_mapping_path)
    print(f"Saved files in {data_dir}.")
    return dataset, dataset_info, ntokens, test_data, test_n_batches, train_data, train_n_batches, val_data, val_n_batches

