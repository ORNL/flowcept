import numpy as np
import random
from time import sleep

import unittest

from flowcept.commons.vocabulary import Status
from flowcept import FlowceptLoop, Flowcept
from flowcept.instrumentation.flowcept_loop import FlowceptLightweightLoop

TIME_TO_SLEEP = 0.001

class LoopTests(unittest.TestCase):

    def flowcept_loop_types(self, flowcept_loop_type):
        if flowcept_loop_type == "lightweight":
            loop_class = FlowceptLightweightLoop
        else:
            loop_class = FlowceptLoop

        if flowcept_loop_type != "lightweight": # We don't support enumare in lightweight
            with Flowcept():
                items = enumerate(range(0, 27 - 1, 20))
                for i, batch in loop_class(items):
                    print(i, batch)
                    continue
            docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
            assert len(docs) == i+1

        with Flowcept():
            items = range(3)
            loop = loop_class(items=items)
            for _ in loop:
                pass
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == len(items)

        with Flowcept():
            items = [10, 20, 30]
            loop = loop_class(items=items)
            for _ in loop:
                pass
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == len(items)

        with Flowcept():
            items = "abcd"
            loop = loop_class(items=items)
            for _ in loop:
                pass
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == len(items)

        with Flowcept():
            items = np.array([0.5, 1.0, 1.5])
            loop = loop_class(items=items, loop_name="our_loop")
            for _ in loop:
                loop.end_iter({"a": 1})
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id,
                                         "activity_id": "our_loop_iteration"})
        assert len(docs) == len(items)
        assert all(d["generated"]["a"] == 1 for d in docs)

        # Unitary range
        with Flowcept():
            epochs_loop = loop_class(items=range(1, 2), loop_name="epochs_loop",
                                       item_name="epoch")
            for _ in epochs_loop:
                sleep(TIME_TO_SLEEP)
                epochs_loop.end_iter({"a": 1})
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == len(epochs_loop)
        assert all(d["status"] == "FINISHED" and d["used"] for d in docs)

        # Two items
        with Flowcept():
            epochs_loop = loop_class(items=range(2), loop_name="epochs_loop",
                                       item_name="epoch", parent_task_id="mock_task123")
            for _ in epochs_loop:
                sleep(TIME_TO_SLEEP)
                epochs_loop.end_iter({"a": 1})
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert all(d["status"] == "FINISHED" for d in docs)
        assert len(docs) == len(epochs_loop)

        if flowcept_loop_type != "lightweight":
            sorted_tasks = sorted(docs, key=lambda x: x['started_at'])
            for i in range(len(sorted_tasks)):
                t = sorted_tasks[i]
                assert t["parent_task_id"] == "mock_task123"
                assert t["activity_id"] == "epochs_loop_iteration"
                assert t["used"]["i"] == i
                assert t["used"]["epoch"] == i

        if flowcept_loop_type != "lightweight":  # We dont support int in lightweight
            # Three items
            with Flowcept():
                # needs to assert that time end > time init for all tasks
                epochs_loop = loop_class(items=3, loop_name="epochs_loop",
                                           item_name="epoch")
                for _ in epochs_loop:
                    sleep(TIME_TO_SLEEP)
                    epochs_loop.end_iter({"a": 1})
            docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
            assert all(d["status"] == "FINISHED" for d in docs)
            assert len(docs) == len(epochs_loop)
            sorted_tasks = sorted(docs, key=lambda x: x['started_at'])
            for i in range(len(sorted_tasks)):
                t = sorted_tasks[i]
                assert t["activity_id"] == "epochs_loop_iteration"
                assert t["used"]["i"] == i
                assert t["used"]["epoch"] == i

        # Empty list
        with Flowcept():
            epochs_loop = loop_class(items=[], loop_name="epochs_loop",
                                       item_name="epoch")
            for _ in epochs_loop:
                sleep(TIME_TO_SLEEP)
                epochs_loop.end_iter({"a": 1})
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == 0

    def test_loops(self):
        self.flowcept_loop_types(flowcept_loop_type="default")
        self.flowcept_loop_types(flowcept_loop_type="lightweight")

    def test_flowcept_loop_generator(self):
        number_of_epochs = 1
        epochs = range(0, number_of_epochs)
        with Flowcept():
            loop = FlowceptLoop(items=epochs, loop_name="epochs", item_name="epoch")
            for e in loop:
                sleep(TIME_TO_SLEEP)
                loss = random.random()
                print(e, loss)
                loop.end_iter({"loss": loss})

        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == number_of_epochs  # 1 (parent_task) + #epochs (sub_tasks)

        iteration_tasks = []
        for d in docs:
            assert d["started_at"] is not None
            assert d["used"]["i"] >= 0
            assert d["generated"]["loss"] > 0
            iteration_tasks.append(d)

        assert len(iteration_tasks) == number_of_epochs
        sorted_iteration_tasks = sorted(iteration_tasks, key=lambda x: x['used']['i'])
        for i in range(len(sorted_iteration_tasks)):
            t = sorted_iteration_tasks[i]
            assert t["used"]["i"] == i
            assert t["used"]["epoch"] == i
            assert t["status"] == Status.FINISHED.value
