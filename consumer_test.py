import mochi.mofka.client as mofka
from mochi.mofka.client import ThreadPool, AdaptiveBatchSize
import json


def data_selector(metadata, descriptor):
    return descriptor

def data_broker(metadata, descriptor):
    return [ bytearray(descriptor.size) ]

driver = mofka.MofkaDriver("/mofka.json")
batch_size = AdaptiveBatchSize
thread_pool = ThreadPool(0)  # THREAD POOL ZERO HERE WORKED, Using THREAD POOL ONE in the PRODUCER with persistence=False
# create a topic
topic_name = "flowcept"

topic = driver.open_topic(topic_name)

consumer_name = "flowcept"
consumer = topic.consumer(name=consumer_name,
                            thread_pool=thread_pool,
                            batch_size=batch_size,
                            data_selector=data_selector,
                            data_broker=data_broker)


while True:
    print("in the loooooop")
    f = consumer.pull()
    event = f.wait()
    print("metadata",json.loads(event.metadata))
