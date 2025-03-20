#!/bin/bash
#PBS -l select=2:system=polaris
#PBS -l place=scatter
#PBS -l filesystems=home:eagle
#PBS -l walltime=00:20:00
#PBS -q debug
#PBS -A recup
#PBS -o test.out
#PBS -e test.err


cd /eagle/projects/radix-io/sockerman/flowcept_mofka/flowcept/

source  /eagle/projects/radix-io/sockerman/spack/share/spack/setup-env.sh
spack env activate flowceptMofka

module use /soft/spack/gcc/0.6.1/install/modulefiles/Core
module load apptainer
#For compute nodes set proxy variable
export HTTP_PROXY=http://proxy.alcf.anl.gov:3128
export HTTPS_PROXY=http://proxy.alcf.anl.gov:3128
export http_proxy=http://proxy.alcf.anl.gov:3128
export https_proxy=http://proxy.alcf.anl.gov:3128


export PYTHONPATH="/eagle/projects/radix-io/sockerman/flowcept_mofka/flowcept/examples/llm_complex:$PYTHONPATH"
export MONGO_ENABLED=false
module use /soft/modulefiles 
module load cudatoolkit-standalone/12.2.2

# mofka
export FLOWCEPT_SETTINGS_PATH=/eagle/projects/radix-io/sockerman/flowcept_mofka/flowcept/resources/sample_settings.yaml


nodes=1
total=$((4 * nodes))

readarray -t all_nodes < "$PBS_NODEFILE"
base_node=${all_nodes[0]}
tail -n +2 $PBS_NODEFILE > worker_nodefile.txt



# launch redis container
mkdir -p $PWD/redisdata
mpiexec -n 1 --ppn 1 --cpu-bind none --hosts $base_node apptainer instance run -C -B redisdata:/data redis.sif flowcept_redis --port 6379 --appendonly yes &
sleep 3
echo "Launched redis container"

# launch bedrock server
mpiexec -n 1 --ppn 1 --cpu-bind none --hosts $base_node bash resources/mofka/bedrock_setup.sh & 


# File to watch
FLAG_FILE="flag.txt"

# Wait until the file exists
while [ ! -f "$FLAG_FILE" ]; do
    sleep 1  # Check every second
done

# Remove the file once detected
rm "$FLAG_FILE"
echo "Launched bedrocker server"

# launch scheduler
rm cluster.info
mpiexec -n 1 --ppn 1 --cpu-bind none --hosts $base_node dask scheduler --scheduler-file cluster.info 2> scheduler.txt 1> scheduler.txt &

FLAG_FILE="cluster.info"
# Wait until the file exists
while [ ! -f "$FLAG_FILE" ]; do
    sleep 1  # Check every second
done
echo "Scheduler online"


mpiexec -n $total --ppn 4 --cpu-bind none --hostfile worker_nodefile.txt dask worker --scheduler-file cluster.info --nthreads 1 --memory-limit 512GB  1> worker.txt 2> worker.txt & 
sleep 3
echo "$total workers launched" 


python3 examples/llm_complex/llm_main_example.py --dask-map-gpus true --scheduler-file cluster.info --with-persistence false --workflow-params='{"input_data_dir": "/eagle/projects/radix-io/sockerman/flowcept_mofka/flowcept/input_data/", "batch_size": 20, "eval_batch_size": 10, "emsize": [200, 400], "nhid": [200, 400], "nlayers": [2, 4, 8], "nhead": [2, 4], "dropout": [0.2], "lr": [0.1], "pos_encoding_max_len": [5000], "subset_size": 10, "epochs": 4, "max_runs": null, "delete_after_run": true, "random_seed": 0, "tokenizer_type": "basic_english"}'


echo "Client closed"

echo "launching consumer"
python3 consumer.py