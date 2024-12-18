import multiprocessing
import random
from time import sleep

from flowcept import Flowcept, FlowceptLoop

if __name__ == '__main__':  #

    interceptor_id = Flowcept.start_instrumentation_interceptor()

    event = multiprocessing.Event()
    process1 = multiprocessing.Process(target=Flowcept.start_persistence, args=(interceptor_id, event))
    process1.start()
    sleep(1)
    # Run loop
    loop = FlowceptLoop(range(max_iterations := 3), workflow_id=interceptor_id)
    for item in loop:
        loss = random.random()
        sleep(0.05)
        print(item, loss)
        # The following is optional, in case you want to capture values generated inside the loop.
        loop.end_iter({"item": item, "loss": loss})

    Flowcept.stop_instrumentation_interceptor()

    event.set()
    process1.join()

    docs = Flowcept.db.query(filter={"workflow_id": interceptor_id})
    for d in docs:
        print(d)
    # assert len(docs) == max_iterations+1  # The whole loop itself is a task

    #
    #
    # @staticmethod
    # def start_instrumentation_interceptor():
    #     instance = InstrumentationInterceptor.get_instance()
    #     instance_id = id(instance)
    #     instance.start(bundle_exec_id=instance_id)
    #     return instance_id
    #
    # @staticmethod
    # def stop_instrumentation_interceptor():
    #     instance = InstrumentationInterceptor.get_instance()
    #     instance.stop()
    #
    # @staticmethod
    # def start_persistence(interceptor_id, event):
    #     from flowcept.flowceptor.consumers.document_inserter import DocumentInserter
    #     inserter = DocumentInserter(
    #         check_safe_stops=True,
    #         bundle_exec_id=interceptor_id,
    #     ).start()
    #     event.wait()
    #     inserter.stop()
