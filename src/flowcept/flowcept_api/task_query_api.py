"""Task module."""

from collections import OrderedDict
from typing import List, Dict, Tuple
from datetime import timedelta
import json

import numpy as np
import pandas as pd
import pymongo
import requests

from bson.objectid import ObjectId

from flowcept.analytics.analytics_utils import (
    clean_dataframe as clean_df,
    analyze_correlations_between,
    find_outliers_zscore,
)
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.query_utils import (
    get_doc_status,
    to_datetime,
    calculate_telemetry_diff_for_docs,
)
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.commons import singleton
from flowcept.configs import WEBSERVER_HOST, WEBSERVER_PORT, ANALYTICS
from flowcept.flowcept_webserver.app import BASE_ROUTE
from flowcept.flowcept_webserver.resources.query_rsrc import TaskQuery


@singleton
class TaskQueryAPI(object):
    """Task class."""

    ASC = pymongo.ASCENDING
    DESC = pymongo.DESCENDING
    MINIMUM_FIRST = ASC
    MAXIMUM_FIRST = DESC

    def __init__(
        self,
        with_webserver=False,
        host: str = WEBSERVER_HOST,
        port: int = WEBSERVER_PORT,
        auth=None,
    ):
        self.logger = FlowceptLogger()
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
                self.logger.debug("Ok, webserver is ready to receive requests.")
            except Exception:
                raise Exception(f"Error when accessing the webserver at {_base_url}")

    def query(
        self,
        filter: Dict = None,
        projection: List[str] = None,
        limit: int = 0,
        sort: List[Tuple] = None,
        aggregation: List[Tuple] = None,
        remove_json_unserializables=True,
    ) -> List[Dict]:
        """Generate a mongo query pipeline.

        Generates a MongoDB query pipeline based on the provided arguments.

        Parameters
        ----------
        filter (dict):
            The filter criteria for the $match stage.
        projection (list, optional):
            List of fields to include in the $project stage. Defaults to None.
        limit (int, optional):
            The maximum number of documents to return. Defaults to 0 (no limit).
        sort (list of tuples, optional):
            List of (field, order) tuples specifying the sorting order. Defaults to None.
        aggregation (list of tuples, optional):
            List of (aggregation_operator, field_name) tuples specifying
            additional aggregation operations. Defaults to None.
        remove_json_unserializables:
            Removes fields that are not JSON serializable. Defaults to True

        Returns
        -------
        list:
            A list with the result set.

        Example
        -------
        Create a pipeline with a filter, projection, sorting, and aggregation.

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
                request_data["remove_json_unserializables"] = remove_json_unserializables

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
            if docs is not None:
                return docs
            else:
                self.logger.error("Error when executing query.")

    def get_subworkflows_tasks_from_a_parent_workflow(self, parent_workflow_id: str) -> List[Dict]:
        """Get subworkflows."""
        db_api = DBAPI()
        sub_wfs = db_api.workflow_query({"parent_workflow_id": parent_workflow_id})
        if not sub_wfs:
            return None
        tasks = []
        for sub_wf in sub_wfs:
            sub_wf_tasks = self.query({"workflow_id": sub_wf.workflow_id})
            tasks.extend(sub_wf_tasks)
        return tasks

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
        clean_dataframe: bool = False,
        keep_non_numeric_columns=False,
        keep_only_nans_columns=False,
        keep_task_id=False,
        keep_telemetry_percent_columns=False,
        sum_lists=False,
        aggregate_telemetry=False,
    ) -> pd.DataFrame:
        """Get dataframe query."""
        # TODO: assert that if clean_dataframe is False, other clean_dataframe
        # related args should be default.
        docs = self.query(
            filter,
            projection,
            limit,
            sort,
            aggregation,
            remove_json_unserializables,
        )
        if len(docs) == 0:
            return pd.DataFrame()

        df = self._get_dataframe_from_task_docs(docs, calculate_telemetry_diff, shift_hours)
        # Clean the telemetry DataFrame if specified
        if clean_dataframe:
            df = clean_df(
                df,
                keep_non_numeric_columns=keep_non_numeric_columns,
                keep_only_nans_columns=keep_only_nans_columns,
                keep_task_id=keep_task_id,
                keep_telemetry_percent_columns=keep_telemetry_percent_columns,
                sum_lists=sum_lists,
                aggregate_telemetry=aggregate_telemetry,
            )
        return df

    def _get_dataframe_from_task_docs(
        self,
        docs: [List[Dict]],
        calculate_telemetry_diff=False,
        shift_hours=0,
    ) -> pd.DataFrame:
        if docs is None:
            raise Exception("Docs is none in _get_dataframe_from_task_docs")

        if calculate_telemetry_diff:
            try:
                docs = calculate_telemetry_diff_for_docs(docs)
            except Exception as e:
                self.logger.exception(e)

        try:
            df = pd.json_normalize(docs)
        except Exception as e:
            self.logger.exception(e)
            return None

        try:
            df["status"] = df.apply(get_doc_status, axis=1)
        except Exception as e:
            self.logger.exception(e)

        try:
            df = df.drop(
                columns=["finished", "error", "running", "submitted"],
                errors="ignore",
            )
        except Exception as e:
            self.logger.exception(e)

        for col in [
            "started_at",
            "ended_at",
            "submitted_at",
            "utc_timestamp",
        ]:
            to_datetime(self.logger, df, col, shift_hours)

        if "_id" in df.columns:
            try:
                df["doc_generated_time"] = df["_id"].apply(
                    lambda _id: ObjectId(_id).generation_time + timedelta(hours=shift_hours)
                )
            except Exception as e:
                self.logger.info(e)

        try:
            df["elapsed_time"] = df["ended_at"] - df["started_at"]
            df["elapsed_time"] = df["elapsed_time"].apply(
                lambda x: x.total_seconds() if isinstance(x, timedelta) else -1
            )
        except Exception as e:
            self.logger.info(e)

        return df

    def get_errored_tasks(self, workflow_id=None, campaign_id=None, filter=None):
        """Get errored tasks."""
        # TODO: implement
        raise NotImplementedError()

    def get_successful_tasks(self, workflow_id=None, campaign_id=None, filter=None):
        """Get successful tasks."""
        # TODO: implement
        raise NotImplementedError()

    def df_get_campaign_tasks(self, campaign_id=None, filter=None):
        """Get campaign tasks."""
        # TODO: implement
        raise NotImplementedError()

    def df_get_top_k_tasks(
        self,
        sort: List[Tuple] = None,
        k: int = 5,
        filter: Dict = None,
        clean_dataframe: bool = False,
        calculate_telemetry_diff: bool = False,
        keep_non_numeric_columns=False,
        keep_only_nans_columns=False,
        keep_task_id=False,
        keep_telemetry_percent_columns=False,
        sum_lists=False,
        aggregate_telemetry=False,
    ):
        """Get top tasks.

        Retrieve the top K tasks from the (optionally telemetry-aware)
        DataFrame based on specified sorting criteria.

        Parameters
        ----------
        - sort (List[Tuple], optional): A list of tuples specifying sorting
          criteria for columns. Each tuple should contain a column name and a
          sorting order, where the sorting order can be TaskQueryAPI.ASC for
          ascending or TaskQueryAPI.DESC for descending.

        - k (int, optional): The number of top tasks to retrieve. Defaults to 5.

        - filter (optional): A filter condition to apply to the DataFrame. It
          should follow pymongo's query filter syntax. See:
          https://www.w3schools.com/python/python_mongodb_query.asp

        - clean_telemetry_dataframe (bool, optional): If True, clean the
          DataFrame using the clean_df function.

        - calculate_telemetry_diff (bool, optional): If True, calculate
          telemetry differences in the DataFrame.

        Returns
        -------
            pandas.DataFrame: A DataFrame containing the top K tasks
            based on the specified sorting criteria.

        Raises
        ------
        - Exception: If a specified column in the sorting criteria is not
          present in the DataFrame.

        - Exception: If an invalid sorting order is provided. Use the
          constants TaskQueryAPI.ASC or TaskQueryAPI.DESC.
        """
        # Retrieve telemetry DataFrame based on filter and calculation options
        df = self.df_query(
            filter=filter,
            calculate_telemetry_diff=calculate_telemetry_diff,
            clean_dataframe=clean_dataframe,
            keep_non_numeric_columns=keep_non_numeric_columns,
            keep_only_nans_columns=keep_only_nans_columns,
            keep_task_id=keep_task_id,
            keep_telemetry_percent_columns=keep_telemetry_percent_columns,
            sum_lists=sum_lists,
            aggregate_telemetry=aggregate_telemetry,
        )

        # Fill NaN values in the DataFrame with np.nan
        df.fillna(value=np.nan, inplace=True)

        # Clean the telemetry DataFrame if specified
        if clean_dataframe:
            df = clean_df(
                df,
                keep_non_numeric_columns=keep_non_numeric_columns,
                keep_only_nans_columns=keep_only_nans_columns,
                keep_task_id=keep_task_id,
                keep_telemetry_percent_columns=keep_telemetry_percent_columns,
                sum_lists=sum_lists,
                aggregate_telemetry=aggregate_telemetry,
            )

        # Sorting criteria validation and extraction
        sort_col_names, sort_col_orders = [], []
        for col_name, order in sort:
            if col_name not in df.columns:
                raise Exception(
                    f"Column {col_name} is not in the dataframe. "
                    f"The available columns are:\n{list(df.columns)}"
                )
            if order not in {TaskQueryAPI.ASC, TaskQueryAPI.DESC}:
                raise Exception("Use TaskQueryAPI.ASC or TaskQueryAPI.DESC for sorting order.")

            sort_col_names.append(col_name)
            sort_col_orders.append((order == TaskQueryAPI.ASC))

        # Sort the DataFrame based on sorting criteria and retrieve the top K rows
        result_df = df.sort_values(by=sort_col_names, ascending=sort_col_orders)
        result_df = result_df.head(k)

        return result_df

    def df_get_tasks_quantiles(
        self,
        clauses: List[Tuple],
        filter=None,
        sort: List[Tuple] = None,
        limit: int = -1,
        clean_dataframe=False,
        keep_non_numeric_columns=False,
        keep_only_nans_columns=False,
        keep_task_id=False,
        keep_telemetry_percent_columns=False,
        sum_lists=False,
        aggregate_telemetry=False,
        calculate_telemetry_diff=False,
    ) -> pd.DataFrame:
        """Get tasks.

        # TODO: write docstring
        :param calculate_telemetry_diff:
        :param clean_dataframe:
        :param filter:
        :param clauses: (col_name,  condition, percentile)
        :param sort: (col_name, ASC or DESC)
        :param limit:
        :return:
        """
        # TODO: :idea: think of finding the clauses, quantile threshold, and
        # sort order automatically
        df = self.df_query(
            filter=filter,
            calculate_telemetry_diff=calculate_telemetry_diff,
            clean_dataframe=clean_dataframe,
            keep_non_numeric_columns=keep_non_numeric_columns,
            keep_only_nans_columns=keep_only_nans_columns,
            keep_task_id=keep_task_id,
            keep_telemetry_percent_columns=keep_telemetry_percent_columns,
            sum_lists=sum_lists,
            aggregate_telemetry=aggregate_telemetry,
        )
        df.fillna(value=np.nan, inplace=True)

        query_parts = []
        for col_name, condition, quantile in clauses:
            if col_name not in df.columns:
                msg = f"Column {col_name} is not in dataframe. "
                raise Exception(msg + f"The available columns are:\n{list(df.columns)}")
            if 0 > quantile > 1:
                raise Exception("Quantile must be 0 < float_number < 1.")
            if condition not in {">", "<", ">=", "<=", "==", "!="}:
                raise Exception("Wrong query format: " + condition)
            quantile_val = df[col_name].quantile(quantile)
            query_parts.append(f"`{col_name}` {condition} {quantile_val}")
        quantiles_query = " & ".join(query_parts)
        self.logger.debug(quantiles_query)
        result_df = df.query(quantiles_query)
        if len(result_df) == 0:
            return result_df

        if sort is not None:
            sort_col_names, sort_col_orders = [], []
            for col_name, order in sort:
                if col_name not in result_df.columns:
                    msg = f"Column {col_name} is not in resulting dataframe. "
                    raise Exception(msg + f"Available columns are:\n{list(result_df.columns)}")
                if order not in {TaskQueryAPI.ASC, TaskQueryAPI.DESC}:
                    raise Exception(
                        "Use TaskQueryAPI.ASC or TaskQueryAPI.DESC to express sorting order."
                    )

                sort_col_names.append(col_name)
                sort_col_orders.append((order == TaskQueryAPI.ASC))

            result_df = result_df.sort_values(by=sort_col_names, ascending=sort_col_orders)

        if limit > 0:
            result_df = result_df.head(limit)

        return result_df

    def find_interesting_tasks_based_on_correlations_generated_and_telemetry_data(
        self, filter=None, correlation_threshold=0.5, top_k=50
    ):
        """Find tasks."""
        return self.find_interesting_tasks_based_on_xyz(
            filter=filter,
            correlation_threshold=correlation_threshold,
            top_k=top_k,
        )

    def find_interesting_tasks_based_on_xyz(
        self,
        pattern_x="^generated[.](?!responsible_ai_metadata[.]).*",  # loss, acc
        pattern_y="^telemetry_diff[.].*",  # telemetry
        pattern_z="^generated[.]responsible_ai_metadata[.].*$",  # params
        filter=None,
        correlation_threshold=0.5,
        top_k=50,
    ):
        """Find tasks.

        Returns the most interesting tasks for which (xy) and (xz) are highly
        correlated, meaning that y is very senstive to x as well as z is very
        sensitive to x. It returns a sorted dict, based on a score calculated
        depending on how many high (xy) and (xz) correlations are found.
        :param pattern_x:
        :param pattern_y:
        :param pattern_z:
        :param filter:
        :param correlation_threshold:
        :param top_k:
        :return:
        """
        self.logger.warning("This is an experimental feature. Use it with carefully!")
        # TODO: improve and optmize this function.
        df = self.df_query(filter=filter, calculate_telemetry_diff=True)
        corr_df1 = analyze_correlations_between(df, pattern_x, pattern_y)
        corr_df2 = analyze_correlations_between(df, pattern_x, pattern_z)

        result_df1 = corr_df1[abs(corr_df1["correlation"]) >= correlation_threshold]
        result_df1 = result_df1.iloc[result_df1["correlation"].abs().argsort()][::-1].head(top_k)

        result_df2 = corr_df2[abs(corr_df2["correlation"]) >= correlation_threshold]
        result_df2 = result_df2.iloc[result_df2["correlation"].abs().argsort()][::-1].head(top_k)
        cols = []
        for index, row in result_df1.iterrows():
            x_col = row["col_1"]
            y_col = row["col_2"]
            x_y_corr = row["correlation"]

            for index2, row2 in result_df2.iterrows():
                # Accessing individual elements in the row
                x_col_df2 = row2["col_1"]
                z_col = row2["col_2"]
                x_z_corr = row2["correlation"]

                if x_col == x_col_df2:
                    cols.append(
                        {
                            "x_col": x_col,
                            "y_col": y_col,
                            "z_col": z_col,
                            "x_y_corr": x_y_corr,
                            "x_z_corr": x_z_corr,
                        }
                    )

        dfa = pd.DataFrame(cols)
        new_rows = []

        ret = {}

        SORT_ORDERS = ANALYTICS["sort_orders"]

        for index, row in dfa.iterrows():
            clauses = [
                (row["y_col"], "<=", 0.5),
            ]
            xcol_sort = TaskQueryAPI.MINIMUM_FIRST
            if SORT_ORDERS is not None and SORT_ORDERS[row["x_col"]] == "maximum_first":
                xcol_sort = TaskQueryAPI.MAXIMUM_FIRST

            sort = [
                (row["y_col"], TaskQueryAPI.MINIMUM_FIRST),  # resources
                (row["x_col"], xcol_sort),  # accuracy
                (row["z_col"], TaskQueryAPI.MINIMUM_FIRST),  # resp_ai
            ]
            try:
                # TODO: we don't need to query the db again! this is slow!!
                df = self.df_get_tasks_quantiles(
                    limit=1,
                    clauses=clauses,
                    filter=filter,
                    sort=sort,
                    calculate_telemetry_diff=True,
                    clean_dataframe=False,
                )
                cols_to_proj = [
                    "task_id",
                    row["x_col"],
                    row["y_col"],
                    row["z_col"],
                ]
                _dict = df[cols_to_proj].to_dict(orient="records")[0]
                _dict["x_y_corr"] = row["x_y_corr"]
                _dict["x_z_corr"] = row["x_z_corr"]
                new_rows.append(_dict)

                tid, x_col, y_col, z_col, x, y, z, xy_corr, xz_corr = (
                    _dict["task_id"],
                    row["x_col"],
                    row["y_col"],
                    row["z_col"],
                    _dict[row["x_col"]],
                    _dict[row["y_col"]],
                    _dict[row["z_col"]],
                    row["x_y_corr"],
                    row["x_z_corr"],
                )
                if tid not in ret:
                    ret[tid] = {
                        "x_cols": [],
                        "y_cols": [],
                        "z_cols": [],
                        "score": 0,
                        "n_x_cols": 0,
                        "n_y_cols": 0,
                        "n_z_cols": 0,
                        "data": {},
                    }

                if x_col not in ret[tid]["x_cols"]:
                    ret[tid]["x_cols"].append(x_col)
                    ret[tid]["n_x_cols"] += 1
                    ret[tid]["score"] += 20
                if y_col not in ret[tid]["y_cols"]:
                    ret[tid]["y_cols"].append(y_col)
                    ret[tid]["n_y_cols"] += 1
                    ret[tid]["score"] += 1
                if z_col not in ret[tid]["z_cols"]:
                    ret[tid]["z_cols"].append(z_col)
                    ret[tid]["n_z_cols"] += 1
                    ret[tid]["score"] += 10

                _data = ret[tid]["data"]
                if x_col not in _data:
                    _data[x_col] = {"value": x, "y": [], "z": []}
                # TODO: We are repeating values here unnecessarily!
                _data[x_col]["y"].append({y_col: y, "xy_corr": xy_corr})
                _data[x_col]["z"].append({z_col: z, "xz_corr": xz_corr})
            except Exception as e:
                print(e)

        scores = []
        for tid in ret:
            scores.append((tid, ret[tid]["score"]))
        sorted_score = sorted(scores, key=lambda _x: _x[1], reverse=True)

        sorted_return = OrderedDict()
        for s in sorted_score:
            sorted_return[s[0]] = ret[s[0]]

        return sorted_return

    def df_find_outliers(
        self,
        filter,
        outlier_threshold=3,
        calculate_telemetry_diff=True,
        clean_dataframe: bool = False,
        keep_non_numeric_columns=False,
        keep_only_nans_columns=False,
        keep_task_id=False,
        keep_telemetry_percent_columns=False,
        sum_lists=False,
        aggregate_telemetry=False,
    ):
        """Find outliers."""
        df = self.df_query(
            filter=filter,
            calculate_telemetry_diff=calculate_telemetry_diff,
            clean_dataframe=clean_dataframe,
            keep_non_numeric_columns=keep_non_numeric_columns,
            keep_only_nans_columns=keep_only_nans_columns,
            keep_task_id=keep_task_id,
            keep_telemetry_percent_columns=keep_telemetry_percent_columns,
            sum_lists=sum_lists,
            aggregate_telemetry=aggregate_telemetry,
        )
        df["outlier_columns"] = df.apply(find_outliers_zscore, axis=1, threshold=outlier_threshold)
        return df[df["outlier_columns"].apply(len) > 0]
