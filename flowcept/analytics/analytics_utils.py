import logging
import numpy as np
import pandas as pd
import re

_CORRELATION_DF_HEADER = ["col_1", "col_2", "correlation"]


def clean_dataframe(
    df: pd.DataFrame,
    logger: logging.Logger = None,
    keep_non_numeric_columns=False,
    keep_only_nans_columns=False,
    keep_task_id=False,
    keep_telemetry_percent_columns=False,
    aggregate_telemetry=False,
) -> pd.DataFrame:
    """

    :param keep_task_id:
    :param keep_only_nans_columns:
    :param keep_non_numeric_columns:
    :param df:
    :param logger:
    :param keep_telemetry_percent_columns:
    :param aggregate_telemetry: We use some very simplistic forms of aggregations just
     to reduce the complexity of the dataframe. Use this feature very carefully as the aggregation may be misleading.
    :return:
    """
    has_telemetry_diff_columns = any(
        col.startswith("telemetry_diff") for col in df.columns
    )

    logmsg = f"Number of columns originally: {len(df.columns)}"
    if logger:
        logger.info(logmsg)
    else:
        print(logmsg)

    regex_str = "used|generated"
    if keep_task_id:
        regex_str += "|task_id"
    if has_telemetry_diff_columns:
        regex_str += "|telemetry_diff"

    # Get only the columns of interest for analysis
    dfa = df.filter(regex=regex_str)

    # Select numeric only columns
    if not keep_non_numeric_columns:
        dfa = dfa.select_dtypes(include=np.number)

    if not keep_only_nans_columns:
        dfa = dfa.loc[:, (dfa != 0).any()]

    # Remove duplicate columns
    dfa_T = dfa.T
    dfa = dfa_T.drop_duplicates(keep="first").T

    if not keep_telemetry_percent_columns and has_telemetry_diff_columns:
        cols_to_drop = [col for col in dfa.columns if "percent" in col]
        dfa.drop(columns=cols_to_drop, inplace=True)

    if aggregate_telemetry and has_telemetry_diff_columns:
        cols_to_drop = []

        network_cols = [
            col
            for col in dfa.columns
            if col.startswith("telemetry_diff.network")
        ]
        dfa["telemetry_diff.network.activity"] = dfa[network_cols].mean(
            axis=1
        )

        io_sum_cols = [col for col in dfa.columns if "disk.io_sum" in col]
        dfa["telemetry_diff.disk.activity"] = dfa[io_sum_cols].mean(axis=1)

        processes_nums_cols = [
            col for col in dfa.columns if "telemetry_diff.process.num_" in col
        ]
        dfa["telemetry_diff.process.activity"] = dfa[processes_nums_cols].sum(
            axis=1
        )

        cols_to_drop.extend(processes_nums_cols)
        cols_to_drop.extend(network_cols)
        cols_to_drop.extend(io_sum_cols)

        cols_to_drop.extend(
            [col for col in dfa.columns if "disk.io_per_disk" in col]
        )

        dfa.drop(columns=cols_to_drop, inplace=True)

    # Removing any leftover cols
    cols_to_drop = [
        col
        for col in dfa.columns
        if "telemetry_at_start" in col or "telemetry_at_end" in col
    ]
    if len(cols_to_drop):
        dfa.drop(columns=cols_to_drop, inplace=True)

    logmsg = f"Number of columns later: {len(dfa.columns)}"
    if logger:
        logger.info(logmsg)
    else:
        print(logmsg)
    return dfa


def _check_correlations(df, method="kendall", threshold=0, col_pattern1=None):
    # Create a mask to select the upper triangle of the correlation matrix
    correlation_matrix = df.corr(method=method, numeric_only=True)
    mask = correlation_matrix.where(
        np.triu(np.ones(correlation_matrix.shape), k=1).astype(bool)
    )
    corrs = []
    if col_pattern1 is not None:
        col_pattern1_re = re.compile(col_pattern1)

    # Iterate through the selected upper triangle of the correlation matrix
    for i in range(len(mask.columns)):
        if col_pattern1 is not None and not col_pattern1_re.match(
            mask.columns[i]
        ):
            continue
        for j in range(i + 1, len(mask.columns)):
            pair = (mask.columns[i], mask.columns[j])
            corr = mask.iloc[i, j]  # Get correlation value
            if abs(corr) > threshold and pair[0] != pair[1]:
                corrs.append(
                    (mask.columns[i], mask.columns[j], round(corr, 2))
                )
    return corrs


def analyze_correlations(df: pd.DataFrame, method="kendall", threshold=0):
    # Create a mask to select the upper triangle of the correlation matrix
    return pd.DataFrame(
        _check_correlations(df, method, threshold),
        columns=_CORRELATION_DF_HEADER,
    )


def analyze_correlation_between(
    df: pd.DataFrame,
    col_pattern1,
    col_pattern2,
    method="kendall",
    threshold=0,
):
    df = df.filter(regex=f"{col_pattern1}|{col_pattern2}")
    return pd.DataFrame(
        _check_correlations(df, method, threshold, col_pattern1),
        columns=_CORRELATION_DF_HEADER,
    )


def analyze_correlations_used_vs_generated(df: pd.DataFrame, threshold=0):
    return analyze_correlation_between(
        df,
        col_pattern1="^used[.]*",
        col_pattern2="^generated[.]*",
        threshold=threshold,
    )


def analyze_correlations_used_vs_telemetry_diff(
    df: pd.DataFrame, threshold=0
):
    return analyze_correlation_between(
        df,
        col_pattern1="^used[.]*",
        col_pattern2="^telemetry_diff[.]*",
        threshold=threshold,
    )


def analyze_correlations_generated_vs_telemetry_diff(
    df: pd.DataFrame, threshold=0
):
    return analyze_correlation_between(
        df,
        col_pattern1="^generated[.]*",
        col_pattern2="^telemetry_diff[.]*",
        threshold=threshold,
    )


def format_number(num):
    suffixes = ["", "K", "M", "B", "T"]
    idx = 0
    while abs(num) >= 1000 and idx < len(suffixes) - 1:
        idx += 1
        num /= 1000.0
    formatted = f"{num:.1f}" if num % 1 != 0 else f"{int(num)}"
    formatted = (
        formatted.rstrip("0").rstrip(".")
        if "." in formatted
        else formatted.rstrip(".")
    )
    return f"{formatted}{suffixes[idx]}"


def describe_col(df, col, label=None):
    label = col if label is None else label
    return {
        "label": label,
        "mean": format_number(df[col].mean()),
        "std": format_number(df[col].std()),
        "min": format_number(df[col].min()),
        "25%": format_number(df[col].quantile(0.25)),
        "50%": format_number(df[col].median()),
        "75%": format_number(df[col].quantile(0.75)),
        "max": format_number(df[col].max()),
    }


def describe_cols(df, cols, col_labels):
    return pd.DataFrame(
        [
            describe_col(df, col, col_label)
            for col, col_label in zip(cols, col_labels)
        ]
    )


def identify_pareto(df):
    datav = df.values
    pareto = []
    for i, point in enumerate(datav):
        if all(np.any(point <= other_point) for other_point in datav[:i]):
            pareto.append(point)
    return pd.DataFrame(pareto, columns=df.columns)
