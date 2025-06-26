"""App module."""

from flask_restful import Api
from flask import Flask

from flowcept.configs import WEBSERVER_HOST, WEBSERVER_PORT
from flowcept.flowcept_webserver.resources.query_rsrc import TaskQuery
from flowcept.flowcept_webserver.resources.task_messages_rsrc import (
    TaskMessages,
)


BASE_ROUTE = "/api"
app = Flask(__name__)
api = Api(app)

api.add_resource(TaskMessages, f"{BASE_ROUTE}/{TaskMessages.ROUTE}")
api.add_resource(TaskQuery, f"{BASE_ROUTE}/{TaskQuery.ROUTE}")


@app.route("/")
def liveness():
    """Livelyness string."""
    return "Server up!"


if __name__ == "__main__":
    app.run(host=WEBSERVER_HOST, port=WEBSERVER_PORT)
