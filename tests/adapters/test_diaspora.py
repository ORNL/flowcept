import threading
import unittest

from flowcept.commons.daos.mq_dao.mq_dao_diaspora import MQDaoDiaspora


class TestMQDaoDiaspora(unittest.TestCase):
    def setUp(self):
        self.dao = MQDaoDiaspora(with_producer=True)

    def test_liveness(self):
        self.assertTrue(self.dao.liveness_test())

    def test_send_and_receive_message(self):
        received = []

        self.dao.subscribe()

        msg = {"task_id": "test-123", "status": "finished"}

        def handler(message):
            if message == msg:
                received.append(message)
                return False  # stop after finding our message
            return True  # keep consuming stale messages

        listener_thread = threading.Thread(
            target=self.dao.message_listener, args=(handler,), daemon=True
        )
        listener_thread.start()

        self.dao.send_message(msg)

        listener_thread.join(timeout=10)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], msg)


if __name__ == "__main__":
    unittest.main()
