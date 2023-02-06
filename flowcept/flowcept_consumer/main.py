import sys
from threading import Thread

from flowcept.commons.doc_db.document_inserter import (
    DocumentInserter,
)


def main():
    document_inserter = DocumentInserter()

    Thread(
        target=document_inserter.main,
    ).start()

    # Next step:
    # kg_inserter = KGInserter()
    # Thread(target=kg_inserter.main,).start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(0)
