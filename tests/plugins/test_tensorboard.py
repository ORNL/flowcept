import unittest
import threading
import time

from flowcept.flowcept_consumer.main import (
    main,
)
from flowcept.flowceptor.plugins.tensorboard.tensorboard_interceptor import (
    TensorboardInterceptor,
)


class TestTensorboard(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestTensorboard, self).__init__(*args, **kwargs)
        self.interceptor = TensorboardInterceptor()
        self.interceptor.state_manager.reset()

    def test_run_tensorboard_hparam_tuning(self):
        """
        Code based on
         https://www.tensorflow.org/tensorboard/hyperparameter_tuning_with_hparams
        :return:
        """
        import os
        import shutil

        logdir = self.interceptor.settings.file_path
        print(logdir)
        if os.path.exists(logdir):
            print("Path exists, gonna delete")
            shutil.rmtree(logdir)

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
                epochs=2,
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
                        hparams = {
                            HP_NUM_UNITS: num_units,
                            HP_DROPOUT: dropout_rate,
                            HP_OPTIMIZER: optimizer,
                            HP_BATCHSIZES: batch_size,
                        }
                        run_name = "run-%d" % session_num
                        print("--- Starting trial: %s" % run_name)
                        print({h.name: hparams[h] for h in hparams})
                        run(f"{logdir}/" + run_name, hparams)
                        session_num += 1

        return logdir

    def _init_consumption(self):
        threading.Thread(target=self.interceptor.observe, daemon=True).start()
        time.sleep(10)
        threading.Thread(target=main, daemon=True).start()
        time.sleep(10)

    def test_observer_and_consumption(self):
        self._init_consumption()
        self.test_run_tensorboard_hparam_tuning()
        time.sleep(60)
        assert self.interceptor.state_manager.count() == 16

    def test_read_tensorboard_hparam_tuning(self):
        logdir = self.test_run_tensorboard_hparam_tuning()

        from tbparse import SummaryReader

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
                                print("Found metric!")
                                break

            if found_metric:
                # Only append if we find a tracked metric in the event
                output.append(msg)
        assert len(output) == 16
