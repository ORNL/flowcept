from typing import List, Dict, Tuple
from datetime import timedelta
import json

import numpy as np
import pandas as pd
import pymongo
import requests

from bson.objectid import ObjectId

from flowcept.analytics.analytics_utils import clean_dataframe as clean_df
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.query_utils import (
    get_doc_status,
    to_datetime,
    calculate_telemetry_diff_for_docs,
)
from flowcept.configs import WEBSERVER_HOST, WEBSERVER_PORT
from flowcept.flowcept_webserver.app import BASE_ROUTE
from flowcept.flowcept_webserver.resources.query_rsrc import TaskQuery


class TaskQueryAPI(object):
    ASC = pymongo.ASCENDING
    DESC = pymongo.DESCENDING

    def __init__(
        self,
        with_webserver=False,
        host: str = WEBSERVER_HOST,
        port: int = WEBSERVER_PORT,
        auth=None,
    ):
        self._logger = FlowceptLogger().get_logger()
        self._with_webserver = with_webserver
        if self._with_webserver:
            self._host = host
            self._port = port
            _base_url = f"http://{self._host}:{self._port}"
            self._url = f"{_base_url}{BASE_ROUTE}{TaskQuery.ROUTE}"
            try:
                r = requests.get(_base_url)
                if r.status_code > 300:
                    raise Exception(r.text)
                self._logger.debug(
                    "Ok, webserver is ready to receive requests."
                )
            except Exception as e:
                raise Exception(
                    f"Error when accessing the webserver at {_base_url}"
                )

    def query(
        self,
        filter: Dict = None,
        projection: List[str] = None,
        limit: int = 0,
        sort: List[Tuple] = None,
        aggregation: List[Tuple] = None,
        remove_json_unserializables=True,
    ) -> List[Dict]:
        """
        Generates a MongoDB query pipeline based on the provided arguments.
        Parameters:
            filter (dict): The filter criteria for the $match stage.
            projection (list, optional): List of fields to include in the $project stage. Defaults to None.
            limit (int, optional): The maximum number of documents to return. Defaults to 0 (no limit).
            sort (list of tuples, optional): List of (field, order) tuples specifying the sorting order. Defaults to None.
            aggregation (list of tuples, optional): List of (aggregation_operator, field_name) tuples
                specifying additional aggregation operations. Defaults to None.
            remove_json_unserializables: removes fields that are not JSON serializable. Defaults to True

        Returns:
            list: A list with the result set.

        Example:
            # Create a pipeline with a filter, projection, sorting, and aggregation
            rs = find(
                filter={"campaign_id": "mycampaign1"},
                projection=["workflow_id", "started_at", "ended_at"],
                limit=10,
                sort=[("workflow_id", ASC), ("end_time", DESC)],
                aggregation=[("avg", "ended_at"), ("min", "started_at")]
            )
        """

        if self._with_webserver:
            request_data = {"filter": json.dumps(filter)}
            if projection:
                request_data["projection"] = json.dumps(projection)
            if limit:
                request_data["limit"] = limit
            if sort:
                request_data["sort"] = json.dumps(sort)
            if aggregation:
                request_data["aggregation"] = json.dumps(aggregation)
            if remove_json_unserializables:
                request_data[
                    "remove_json_unserializables"
                ] = remove_json_unserializables

            r = requests.post(self._url, json=request_data)
            if 200 <= r.status_code < 300:
                return r.json()
            else:
                raise Exception(r.text)

        else:
            dao = DocumentDBDao()
            docs = dao.task_query(
                filter,
                projection,
                limit,
                sort,
                aggregation,
                remove_json_unserializables,
            )
            if docs:
                return docs
            else:
                self._logger.error("Error when executing query.")

    def df_query(
        self,
        filter: Dict = None,
        projection: List[str] = None,
        limit: int = 0,
        sort: List[Tuple] = None,
        aggregation: List[Tuple] = None,
        remove_json_unserializables=True,
        calculate_telemetry_diff=False,
        shift_hours: int = 0,
    ) -> pd.DataFrame:
        docs = self.query(
            filter,
            projection,
            limit,
            sort,
            aggregation,
            remove_json_unserializables,
        )
        df = self._get_dataframe_from_task_docs(
            docs, calculate_telemetry_diff, shift_hours
        )
        return df

    def _get_dataframe_from_task_docs(
        self,
        docs: [List[Dict]],
        calculate_telemetry_diff=False,
        shift_hours=0,
    ) -> pd.DataFrame:
        if calculate_telemetry_diff:
            try:
                docs = calculate_telemetry_diff_for_docs(docs)
            except Exception as e:
                self._logger.exception(e)

        try:
            df = pd.json_normalize(docs)
        except Exception as e:
            self._logger.exception(e)
            return None

        try:
            df["status"] = df.apply(get_doc_status, axis=1)
        except Exception as e:
            self._logger.exception(e)

        try:
            df = df.drop(
                columns=["finished", "error", "running", "submitted"],
                errors="ignore",
            )
        except Exception as e:
            self._logger.exception(e)

        for col in [
            "started_at",
            "ended_at",
            "submitted_at",
            "utc_timestamp",
        ]:
            to_datetime(self._logger, df, col, shift_hours)

        if "_id" in df.columns:
            try:
                df["doc_generated_time"] = df["_id"].apply(
                    lambda _id: ObjectId(_id).generation_time
                    + timedelta(hours=shift_hours)
                )
            except Exception as e:
                self._logger.exception(e)

        try:
            df["elapsed_time"] = df["ended_at"] - df["started_at"]
            df["elapsed_time"] = df["elapsed_time"].apply(
                lambda x: x.total_seconds()
                if isinstance(x, timedelta)
                else -1
            )
        except Exception as e:
            self._logger.exception(e)

        return df

    def get_errored_tasks(
        self, workflow_id=None, campaign_id=None, filter=None
    ):
        # TODO: implement
        raise NotImplementedError()

    def get_successful_tasks(
        self, workflow_id=None, campaign_id=None, filter=None
    ):
        # TODO: implement
        raise NotImplementedError()

    def df_get_campaign_tasks(self, campaign_id=None, filter=None):
        # TODO: implement
        raise NotImplementedError()

    def df_get_top_k_tasks(
        self,
        sort: List[Tuple] = None,
        k: int = 5,
        filter: Dict = None,
        clean_telemetry_dataframe: bool = False,
        calculate_telemetry_diff: bool = False,
    ):
        """
        Retrieve the top K tasks from the (optionally telemetry-aware) DataFrame based on specified sorting criteria.

        Parameters:
        - sort (List[Tuple], optional): A list of tuples specifying sorting criteria for columns. Each tuple should contain
          a column name and a sorting order, where the sorting order can be TaskQueryAPI.ASC for ascending or
          TaskQueryAPI.DESC for descending.
        - k (int, optional): The number of top tasks to retrieve. Defaults to 5.
        - filter (optional): A filter condition to apply to the DataFrame. It should follow pymongo's query filter syntax. See: https://www.w3schools.com/python/python_mongodb_query.asp
        - clean_telemetry_dataframe (bool, optional): If True, clean the DataFrame using the clean_df function.
        - calculate_telemetry_diff (bool, optional): If True, calculate telemetry differences in the DataFrame.

        Returns:
        pandas.DataFrame: A DataFrame containing the top K tasks based on the specified sorting criteria.

        Raises:
        - Exception: If a specified column in the sorting criteria is not present in the DataFrame.
        - Exception: If an invalid sorting order is provided. Use the constants TaskQueryAPI.ASC or TaskQueryAPI.DESC.
        """
        # Retrieve telemetry DataFrame based on filter and calculation options
        df = self.df_query(
            filter=filter, calculate_telemetry_diff=calculate_telemetry_diff
        )

        # Fill NaN values in the DataFrame with np.nan
        df.fillna(value=np.nan, inplace=True)

        # Clean the telemetry DataFrame if specified
        if clean_telemetry_dataframe:
            df = clean_df(df)

        # Sorting criteria validation and extraction
        sort_col_names, sort_col_orders = [], []
        for col_name, order in sort:
            if col_name not in df.columns:
                raise Exception(
                    f"Column {col_name} is not in the dataframe. "
                    f"The available columns are:\n{list(df.columns)}"
                )
            if order not in {TaskQueryAPI.ASC, TaskQueryAPI.DESC}:
                raise Exception(
                    f"Use the constants TaskQueryAPI.ASC or TaskQueryAPI.DESC to express the sorting order."
                )

            sort_col_names.append(col_name)
            sort_col_orders.append((order == TaskQueryAPI.ASC))

        # Sort the DataFrame based on sorting criteria and retrieve the top K rows
        result_df = df.sort_values(
            by=sort_col_names, ascending=sort_col_orders
        )
        result_df = result_df.head(k)

        return result_df

    def df_get_tasks_quantiles(
        self,
        clauses: List[Tuple],
        filter=None,
        sort: List[Tuple] = None,
        limit: int = -1,
        clean_dataframe=False,
        calculate_telemetry_diff=False,
    ) -> pd.DataFrame:
        """
        # TODO: write docstring
        :param calculate_telemetry_diff:
        :param clean_dataframe:
        :param filter:
        :param clauses: (col_name,  condition, percentile)
        :param sort: (col_name, ASC or DESC)
        :param limit:
        :return:
        """
        # TODO: idea: think of finding the clauses and threshold automatically
        df = self.df_query(
            filter=filter, calculate_telemetry_diff=calculate_telemetry_diff
        )
        df.fillna(value=np.nan, inplace=True)
        if clean_dataframe:
            df = clean_df(df)

        query_parts = []
        for col_name, condition, quantile in clauses:
            if col_name not in df.columns:
                raise Exception(
                    f"Column {col_name} is not in the dataframe. The available columns are:\n{list(df.columns)}"
                )
            if 0 > quantile > 1:
                raise Exception("Quantile must be 0 < float_number < 1.")
            if condition not in {">", "<", ">=", "<=", "==", "!="}:
                raise Exception("Wrong query format: " + condition)
            quantile_val = df[col_name].quantile(quantile)
            query_parts.append(f"`{col_name}` {condition} {quantile_val}")
        quantiles_query = " & ".join(query_parts)
        self._logger.debug(quantiles_query)
        result_df = df.query(quantiles_query)
        if len(result_df) == 0:
            return result_df

        if sort is not None:
            sort_col_names, sort_col_orders = [], []
            for col_name, order in sort:
                if col_name not in result_df.columns:
                    raise Exception(
                        f"Column {col_name} is not in the resulting dataframe. The available columns are:\n{list(result_df.columns)}"
                    )
                if order not in {TaskQueryAPI.ASC, TaskQueryAPI.DESC}:
                    raise Exception(
                        f"Use the constants TaskQueryAPI.ASC or TaskQueryAPI.DESC to express the sorting order."
                    )

                sort_col_names.append(col_name)
                sort_col_orders.append((order == TaskQueryAPI.ASC))

            result_df = result_df.sort_values(
                by=sort_col_names, ascending=sort_col_orders
            )

        if limit > 0:
            result_df = result_df.head(limit)

        return result_df
