bash /start_bedrock.sh
python consumer_test.py &
sleep 0.3
python simple_example.py
sleep 1
pkill -9 python
pkill -9 python 
pkill -9 python

