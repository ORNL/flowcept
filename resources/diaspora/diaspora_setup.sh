diaspora-ctl topic create --name interception \
                          --driver files \
                          --driver.root_path /tmp/diaspora-data/ \
                          --topic.num_partitions 1
sleep 1

echo "Created topic."
while true; do sleep 3600; done

