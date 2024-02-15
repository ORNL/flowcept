import time
from time import sleep
from typing import Callable

from flowcept.commons.daos.document_db_dao import DocumentDBDao


def assert_by_querying_task_collections_until(
    doc_dao: DocumentDBDao,
    filter,
    condition_to_evaluate: Callable = None,
    max_trials=10,
    max_time=60,
):
    start_time = time.time()
    trials = 0

    while (time.time() - start_time) < max_time and trials < max_trials:
        docs = doc_dao.task_query(filter)
        if condition_to_evaluate is None:
            if docs is not None and len(docs):
                return True
        else:
            try:
                if condition_to_evaluate(docs):
                    return True
            except:
                pass

        trials += 1
        sleep(1)

    return False
