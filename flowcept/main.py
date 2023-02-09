import sys
from threading import Thread

from flowcept.flowceptor.consumers.document_inserter import (
    DocumentInserter,
)


def main():
    document_inserter = DocumentInserter()

    Thread(
        target=document_inserter._start,
    ).start()



if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
