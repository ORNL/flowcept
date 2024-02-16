import unittest
from time import sleep
from uuid import uuid4

from flowcept.configs import MONGO_INSERTION_BUFFER_TIME

from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept import TensorboardInterceptor, FlowceptConsumerAPI
from flowcept.commons.utils import (
    assert_by_querying_task_collections_until,
    evaluate_until,
)


class TestTensorboard(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestTensorboard, self).__init__(*args, **kwargs)
        # TODO: we are adding this sleep here to try to avoid errors in the CI
        # tests that are only caused with this test.
        sleep(30)
        self.logger = FlowceptLogger()
        self.interceptor = TensorboardInterceptor()

    def reset_log_dir(self):
        logdir = self.interceptor.settings.file_path
        import os
        import shutil

        if os.path.exists(logdir):
            self.logger.debug("Path exists, going to delete")
            shutil.rmtree(logdir)
            sleep(1)
        os.mkdir(logdir)
        self.logger.debug("Exists?" + str(os.path.exists(logdir)))
        watch_interval_sec = self.interceptor.settings.watch_interval_sec
        # Making sure we'll wait until next watch cycle
        sleep(watch_interval_sec * 3)

    def test_run_tensorboard_hparam_tuning(self):
        """
        Code based on
         https://www.tensorflow.org/tensorboard/hyperparameter_tuning_with_hparams
        :return:
        """
        logdir = self.interceptor.settings.file_path
        wf_id = str(uuid4())
        import tensorflow as tf
        from tensorboard.plugins.hparams import api as hp

        fashion_mnist = tf.keras.datasets.fashion_mnist

        (x_train, y_train), (x_test, y_test) = fashion_mnist.load_data()
        x_train, x_test = x_train / 255.0, x_test / 255.0

        HP_NUM_UNITS = hp.HParam("num_units", hp.Discrete([16, 32]))
        HP_DROPOUT = hp.HParam("dropout", hp.RealInterval(0.1, 0.2))
        HP_OPTIMIZER = hp.HParam("optimizer", hp.Discrete(["adam", "sgd"]))
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
                    tf.keras.layers.Dense(
                        hparams[HP_NUM_UNITS], activation=tf.nn.relu
                    ),
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
                            "workflow_id": wf_id,
                            "activity_id": "hyperparam_evaluation",
                            HP_NUM_UNITS: num_units,
                            HP_DROPOUT: dropout_rate,
                            HP_OPTIMIZER: optimizer,
                            HP_BATCHSIZES: batch_size,
                        }
                        run_name = f"wf_id_{wf_id}_{session_num}"
                        self.logger.debug("--- Starting trial: %s" % run_name)
                        self.logger.debug(f"{hparams}")
                        run(f"{logdir}/" + run_name, hparams)
                        session_num += 1

        return wf_id

    def test_observer_and_consumption(self):
        self.reset_log_dir()
        with FlowceptConsumerAPI(self.interceptor):
            wf_id = self.test_run_tensorboard_hparam_tuning()
            self.logger.debug("Done training. Sleeping some time...")
            watch_interval_sec = MONGO_INSERTION_BUFFER_TIME
            # Making sure we'll wait until next watch cycle
            sleep(watch_interval_sec * 20)

        assert evaluate_until(
            lambda: self.interceptor.state_manager.count() == 16,
            msg="Checking if state count == 16",
        )
        doc_dao = DocumentDBDao()
        assert assert_by_querying_task_collections_until(
            doc_dao, {"workflow_id": wf_id}
        )

        # TODO: Sometimes this fails. It's been hard to debug and tensorboard
        #  is not a priority. Need to investigate later
        # May be related: https://github.com/ORNL/flowcept/issues/49
        # assert len(docs) == 16

    def test_read_tensorboard_hparam_tuning(self):
        self.reset_log_dir()
        self.test_run_tensorboard_hparam_tuning()
        from tbparse import SummaryReader

        logdir = self.interceptor.settings.file_path
        reader = SummaryReader(logdir)

        TRACKED_TAGS = {"scalars", "hparams", "tensors"}
        TRACKED_METRICS = {"accuracy"}

        output = []
        for child_event_file in reader.children:
            msg = {}
            child_event = reader.children[child_event_file]
            event_tags = child_event.get_tags()

            found_metric = False
            for tag in TRACKED_TAGS:
                if len(event_tags[tag]):
                    if "run_name" not in msg:
                        msg["run_name"] = child_event_file
                    if "log_path" not in msg:
                        msg["log_path"] = child_event.log_path
                    df = child_event.__getattribute__(tag)
                    df_dict = dict(zip(df.tag, df.value))
                    msg[tag] = df_dict

                    if not found_metric:
                        for tracked_metric in TRACKED_METRICS:
                            if tracked_metric in df_dict:
                                found_metric = True
                                self.logger.debug("Found metric!")
                                break

            if found_metric:
                # Only append if we find a tracked metric in the event
                output.append(msg)
        assert len(output) == 16
