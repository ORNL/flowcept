export HG_LOG_LEVEL=error
export FI_LOG_LEVEL=Trace
rm -rf mofka.json

pkill -9 bedrock
bedrock cxi -c resources/mofka/mofka_config.json &

FILE="mofka.json"
while [ ! -f "$FILE" ]; do
    sleep 1  # Wait 1 second before checking again
done


mofkactl topic create interception --groupfile mofka.json
mofkactl partition add interception --type memory --rank 0 --groupfile mofka.json
                       
sleep 1

touch flag.txt

echo "Created topic."
while true; do sleep 3600; done

