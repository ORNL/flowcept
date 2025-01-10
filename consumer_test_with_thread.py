from threading import Thread
import mochi.mofka.client as mofka
import json


def consumer_loop():
    while True:
        print("in the loooooop")
        f = consumer.pull()
        print("Got Future", f)
        event = f.wait()
        print("metadata",json.loads(event.metadata))


driver = mofka.MofkaDriver("/mofka.json")
topic = driver.open_topic("flowcept")
consumer = topic.consumer(name="flowcept_consumer")

thread = Thread(target=consumer_loop)
thread.start()
print("Started thread.")

# The reason why we need threads in Flowcept is because I start the consumer and producer as different threads in the same process.
# While the consumer is waiting in its consumer_loop, I need the producer thread to keep sending messages.
# Then, when the producer is done, it sends a stop message to the consumer.
# When the consumer receives this stop message, it breaks the consumer_loop and joins its thread, so everything can stop gracefully.
