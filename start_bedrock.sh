rm -f mofka.json
pkill -9 bedrock
sleep 0.1
bedrock tcp://:9999 -c /config.json &
command_pid=$!
sleep 0.3
mofkactl topic create flowcept --groupfile /mofka.json
mofkactl partition add flowcept --type memory --rank 0 --groupfile /mofka.json
sleep 0.3
echo "Created topic."

echo "Bedrock running on PID=$command_pid"

