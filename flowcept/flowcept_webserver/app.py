from flask_restful import Api
from flask import Flask, request, jsonify

from flowcept.configs import WEBSERVER_HOST, WEBSERVER_PORT
from flowcept.flowcept_webserver.resources.query_rsrc import DocQuery
from flowcept.flowcept_webserver.resources.task_messages_rsrc import (
    TaskMessages,
)


BASE_ROUTE = "/api"
app = Flask(__name__)
api = Api(app)

api.add_resource(TaskMessages, f"{BASE_ROUTE}/{TaskMessages.ROUTE}")
api.add_resource(DocQuery, f"{BASE_ROUTE}/{DocQuery.ROUTE}")


@app.route("/")
def liveness():
    return "Server up!"


if __name__ == "__main__":
    app.run(host=WEBSERVER_HOST, port=WEBSERVER_PORT)
