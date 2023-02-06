import json
from flask import jsonify
from flask_restful import Resource, reqparse

from flowcept.commons.doc_db.document_db_dao import DocumentDBDao


class DocQuery(Resource):
    ROUTE = "/doc_query"

    def post(self):
        parser = reqparse.RequestParser()
        req_args = ["filter", "projection", "sort", "limit"]
        for arg in req_args:
            parser.add_argument(arg, type=str, required=False, help="")
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
        docs = dao.find(**doc_args)

        try:
            if docs is not None and len(docs):
                return docs, 201
            else:
                return f"Could not find matching docs", 404
        except Exception as e:
            return f"Sorry, could not jsonify: {e}", 500
