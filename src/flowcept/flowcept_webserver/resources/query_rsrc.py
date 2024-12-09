"""Query resources."""

from datetime import datetime
import json
from flask_restful import Resource, reqparse

from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO
from flowcept.commons.utils import datetime_to_str


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

        dao = MongoDBDAO()
        docs = dao.task_query(**doc_args)

        # Deal with non-serializable datetimes that may come from the databas
        for doc in docs:
            for key, value in doc.items():
                if isinstance(value, datetime):
                    doc[key] = datetime_to_str(value)

        if docs is not None and len(docs):
            return docs, 201
        else:
            return "Could not find matching docs", 404
