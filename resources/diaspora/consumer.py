import json
import os
import time
import csv
from diaspora_stream.api import Driver
print("about to start", flush=True)

driver_options = {
    "root_path": "/tmp/diaspora-data/",
}
driver = Driver(backend="files", options=driver_options)
# create a topic
topic_name = "interception"
consumer_name = "flowcept"
topic = driver.open_topic(topic_name)

consumer = topic.consumer(name=consumer_name)

# Get the list of files in the current directory
csv_files = [file for file in os.listdir() if file.endswith('.csv')]
threshold = len(csv_files)
print("about to start with breakpoint ",threshold, flush=True)
while True:
    data = []
    metadata = []
    t1 = time.time()
    f = consumer.pull()
    event = f.wait(timeout_ms=1)
    while not f.completed():
        event = f.wait(timeout_ms=10)
    t2 = time.time()
    if event:
        e = event.metadata
        print(e)
    else:
        print("END event")
        break






