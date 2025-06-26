import mochi.mofka.client as mofka
from mochi.mofka.client import ThreadPool, AdaptiveBatchSize
import json
import os
import time
import csv
print("about to start", flush=True)
driver = mofka.MofkaDriver("mofka.json")
batch_size = AdaptiveBatchSize
thread_pool = ThreadPool(0)
# create a topic
topic_name = "interception"
topic = driver.open_topic(topic_name)
consumer_name = "flowcept"
consumer = topic.consumer(name=consumer_name,
                            thread_pool=thread_pool,
                            batch_size=batch_size)

pulls = []
events = []
count = 0


# Get the list of files in the current directory
csv_files = [file for file in os.listdir() if file.endswith('.csv')]
threshold = len(csv_files)
print("about to start with breakpoint ",threshold, flush=True)
while True:
    data = []
    metadata = []
    t1 = time.time()
    f = consumer.pull()
    event = f.wait()
    t2 = time.time()
    e = json.loads(event.metadata)


    events.append(e)
    pulls.append(t2 - t1)
    # print("h: ", e.keys(),flush=True)
    
    # break

    if "type" in e.keys() and 'info' in e.keys():
        if e['type'] == 'flowcept_control':
            if e['info'] == "mq_dao_thread_stopped":
                print(e,flush=True)
                count += 1
                with open("data.json", 'w') as f:
                    json.dump(events, f, indent=4)
                with open("pulls.csv", "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(pulls)
        
    if count == threshold:
        break


    

    
    