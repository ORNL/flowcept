# Flowcept

[![Docker Image CI](https://github.com/ORNL/flowcept/actions/workflows/docker-image.yml/badge.svg?branch=main)](https://github.com/ORNL/flowcept/actions/workflows/docker-image.yml)

## Redis for local interceptions
```$ docker run -p 6379:6379  --name redis -d redis```

## RabbitMQ for Zambeze plugin
```$ docker run -it --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3.11-management```
