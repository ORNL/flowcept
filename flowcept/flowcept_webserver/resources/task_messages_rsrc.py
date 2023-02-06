from flask import Flask
from flask_restful import Resource, Api, reqparse

from flowcept.commons.doc_db.document_db_dao import DocumentDBDao


class TaskMessages(Resource):
    ROUTE = "/task_messages"

    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("task_id", type=str, required=False)  # add args
        args = parser.parse_args()

        filter = {}
        if "task_id" in args["task_id"]:
            filter = {"task_id": args["task_id"]}

        dao = DocumentDBDao()
        docs = dao.find(filter)
        return {docs}, 200
