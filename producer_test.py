import sys
import pymargo.core
from pymargo.core import Engine
from mochi.mofka.client import MofkaDriver
from datetime import datetime

import pytz

# Define the Eastern Time zone
eastern_time_zone = pytz.timezone("US/Eastern")


print("Starting driver")
driver = MofkaDriver("/mofka.json")
print("Starting topic")
topic = driver.open_topic("flowcept")
print("Starting producer")
producer = topic.producer()

print("Pushing")

current_time = datetime.now(eastern_time_zone)

# Format the time in a friendly format

friendly_time = current_time.strftime("%A, %B %d, %Y at %I:%M:%S.%f %p %Z")
msg = {"time": friendly_time, "name": "bob"}
print(f"Sending {msg}")
future = producer.push(metadata=msg)
print("Flushing")
producer.flush()
print("Flushed")
