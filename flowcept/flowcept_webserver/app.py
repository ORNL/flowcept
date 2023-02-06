from flask_restful import Api
from flask import Flask, request, jsonify

from flowcept.flowcept_webserver.resources.task_messages_rsrc import (
    TaskMessages,
)


QUERY_ROUTE = "/query"
app = Flask(__name__)
api = Api(app)
api.add_resource(TaskMessages, f"{QUERY_ROUTE}/{TaskMessages.ROUTE}")


@app.route("/")
def liveness():
    return "Server up!"


if __name__ == "__main__":
    app.run()
