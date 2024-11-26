
import mochi.mofka.client as mofka
from mochi.mofka.client import ThreadPool, AdaptiveBatchSize
import json


def data_selector(metadata, descriptor):
    return descriptor

def data_broker(metadata, descriptor):
    return [ bytearray(descriptor.size) ]

driver = mofka.MofkaDriver("mofka.json")
batch_size = AdaptiveBatchSize
thread_pool = ThreadPool(0)
# create a topic
topic_name = "flowcept"

topic = driver.open_topic(topic_name)

consumer_name = "flowcept"
consumer = topic.consumer(name=consumer_name,
                            thread_pool=thread_pool,
                            batch_size=batch_size,
                            data_selector=data_selector,
                            data_broker=data_broker)

print("before while in consumer ")
while True:
    data = []
    metadata = []
    f = consumer.pull()
    event = f.wait()
    print(json.loads(event.metadata))
