# Experimental Settings: March 18

Launch command


```
python3 examples/llm_complex/llm_main_example.py --dask-map-gpus true --scheduler-file cluster.info --with-persistence false --workflow-params='{"input_data_dir": "/eagle/projects/radix-io/sockerman/flowcept_mofka/flowcept/'$myDIR'/input_data/", "batch_size": 20, "eval_batch_size": 10, "emsize": [200, 400], "nhid": [200, 400], "nlayers": [2, 4, 8], "nhead": [2, 4], "dropout": [0.2], "lr": [0.1], "pos_encoding_max_len": [5000], "subset_size": 10, "epochs": 1, "max_runs": null, "delete_after_run": true, "random_seed": 0, "tokenizer_type": "basic_english"}'

```