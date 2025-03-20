# Make sure you run `pip install flowcept[tensorboard]` first.
import uuid
from time import sleep

from flowcept import Flowcept
from flowcept.configs import settings


def run_tensorboard_hparam_tuning(logdir):
    """
    Code based on
     https://www.tensorflow.org/tensorboard/hyperparameter_tuning_with_hparams
    :return:
    """
    import tensorflow as tf
    from tensorboard.plugins.hparams import api as hp

    fashion_mnist = tf.keras.datasets.fashion_mnist

    (x_train, y_train), (x_test, y_test) = fashion_mnist.load_data()
    x_train, x_test = x_train / 255.0, x_test / 255.0

    # Reduce the dataset size for faster debugging
    DEBUG_SAMPLES_TRAIN = 100  # Number of training samples to keep
    DEBUG_SAMPLES_TEST = 20  # Number of test samples to keep

    x_train, y_train = x_train[:DEBUG_SAMPLES_TRAIN], y_train[:DEBUG_SAMPLES_TRAIN]
    x_test, y_test = x_test[:DEBUG_SAMPLES_TEST], y_test[:DEBUG_SAMPLES_TEST]

    HP_NUM_UNITS = hp.HParam("num_units", hp.Discrete([16, 32]))
    HP_DROPOUT = hp.HParam("dropout", hp.RealInterval(0.1, 0.2))
    HP_OPTIMIZER = hp.HParam("optimizer", hp.Discrete(["adam", "sgd"]))
    # HP_BATCHSIZES = hp.HParam("batch_size", hp.Discrete([32, 64]))
    HP_BATCHSIZES = hp.HParam("batch_size", hp.Discrete([32, 64]))

    HP_MODEL_CONFIG = hp.HParam("model_config")
    HP_OPTIMIZER_CONFIG = hp.HParam("optimizer_config")

    METRIC_ACCURACY = "accuracy"

    with tf.summary.create_file_writer(logdir).as_default():
        hp.hparams_config(
            hparams=[
                HP_NUM_UNITS,
                HP_DROPOUT,
                HP_OPTIMIZER,
                HP_BATCHSIZES,
                HP_MODEL_CONFIG,
                HP_OPTIMIZER_CONFIG,
            ],
            metrics=[hp.Metric(METRIC_ACCURACY, display_name="Accuracy")],
        )

    def train_test_model(hparams, logdir):
        model = tf.keras.models.Sequential(
            [
                tf.keras.layers.Flatten(),
                tf.keras.layers.Dense(hparams[HP_NUM_UNITS], activation=tf.nn.relu),
                tf.keras.layers.Dropout(hparams[HP_DROPOUT]),
                tf.keras.layers.Dense(10, activation=tf.nn.softmax),
            ]
        )
        model.compile(
            optimizer=hparams[HP_OPTIMIZER],
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )

        model.fit(
            x_train,
            y_train,
            epochs=1,
            callbacks=[
                tf.keras.callbacks.TensorBoard(logdir),
                # log metrics
                hp.KerasCallback(logdir, hparams),  # log hparams
            ],
            batch_size=hparams[HP_BATCHSIZES],
        )  # Run with 1 epoch to speed things up for tests
        _, accuracy = model.evaluate(x_test, y_test)
        return accuracy

    def run(run_dir, hparams):
        with tf.summary.create_file_writer(run_dir).as_default():
            hp.hparams(hparams)  # record the values used in this trial
            accuracy = train_test_model(hparams, logdir)
            tf.summary.scalar(METRIC_ACCURACY, accuracy, step=1)

    session_num = 0

    for num_units in HP_NUM_UNITS.domain.values:
        for dropout_rate in (
            HP_DROPOUT.domain.min_value,
            HP_DROPOUT.domain.max_value,
        ):
            for optimizer in HP_OPTIMIZER.domain.values:
                for batch_size in HP_BATCHSIZES.domain.values:
                    # These two added ids below are optional and useful
                    # just to contextualize this run.
                    hparams = {
                        "activity_id": "hyperparam_evaluation",
                        HP_NUM_UNITS: num_units,
                        HP_DROPOUT: dropout_rate,
                        HP_OPTIMIZER: optimizer,
                        HP_BATCHSIZES: batch_size,
                    }
                    run_name = f"wf_id_{wf_id}_{session_num}"
                    print("--- Starting trial: %s" % run_name)
                    print(f"{hparams}")
                    run(f"{logdir}/" + run_name, hparams)
                    session_num += 1

    return wf_id


def reset_tensorboard_dir(logdir, watch_interval_sec):
    import os
    import shutil

    if os.path.exists(logdir):
        print("Path exists, going to delete")
        shutil.rmtree(logdir)
        sleep(1)
    os.mkdir(logdir)
    print("Tensorboard directory exists? " + str(os.path.exists(logdir)))
    print(f"Waiting {watch_interval_sec} seconds after directory reset.")
    sleep(watch_interval_sec)


if __name__ == "__main__":
    # Starting the interceptor
    logdir = settings["adapters"]["tensorboard"]["file_path"]
    print(f"Tensorboard dir: {logdir}")
    wf_id = str(uuid.uuid4())
    reset_tensorboard_dir(logdir, 10)

    with Flowcept("tensorboard", workflow_id=wf_id):
        wf_id = run_tensorboard_hparam_tuning(logdir)
        wait_time = 10
        print(f"Done training. Waiting {wait_time} seconds.")
        sleep(wait_time)

    tasks = Flowcept.db.query(filter={"workflow_id": wf_id})
    assert len(tasks) == 16
    print(len(tasks))
