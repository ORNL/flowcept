"""Query resources."""

import json
from flask_restful import Resource, reqparse

from flowcept.commons.daos.document_db_dao import DocumentDBDao


class TaskQuery(Resource):
    """TaskQuery class."""

    ROUTE = "/task_query"

    def post(self):
        """Post it."""
        parser = reqparse.RequestParser()
        req_args = ["filter", "projection", "sort", "limit", "aggregation"]
        for arg in req_args:
            parser.add_argument(arg, type=str, required=False, help=arg)
        args = parser.parse_args()

        doc_args = {}
        for arg in args:
            if args[arg] is None:
                continue
            try:
                doc_args[arg] = json.loads(args[arg])
            except Exception as e:
                return f"Could not parse {arg} argument: {e}", 400

        dao = DocumentDBDao()
        docs = dao.task_query(**doc_args)

        if docs is not None and len(docs):
            return docs, 201
        else:
            return "Could not find matching docs", 404
