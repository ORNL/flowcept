"""Module for TaskMessages object."""

from flask import jsonify, request
from flask_restful import Resource

from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO


class TaskMessages(Resource):
    """TaskMessages class."""

    ROUTE = "/task_messages"

    def get(self):
        """Get something."""
        args = request.args
        task_id = args.get("task_id", None)
        filter = {}
        if task_id is not None:
            filter = {"task_id": task_id}

        dao = MongoDBDAO()
        docs = dao.task_query(filter)
        if len(docs):
            return jsonify(docs), 201
        else:
            return "No tasks found.", 404
