"""Analytics utility module."""

import logging
import numbers
import numpy as np
import pandas as pd

pd.options.mode.chained_assignment = None

_CORRELATION_DF_HEADER = ["col_1", "col_2", "correlation"]


def is_list(val):
    """Check if list."""
    if type(val) in {list, np.array, pd.Series}:
        return True
    return False


def flatten_list_with_sum(val):
    """Flatten list with sum."""
    _sum = 0
    if is_list(val):
        for el in val:
            if is_list(el):
                _sum += flatten_list_with_sum(el)
            else:
                if isinstance(el, numbers.Number) and not np.isnan(el):
                    _sum += el
    else:
        _sum += val
    return _sum


def clean_dataframe(
    df: pd.DataFrame,
    logger: logging.Logger = None,
    keep_non_numeric_columns=False,
    keep_only_nans_columns=False,
    keep_task_id=False,
    keep_telemetry_percent_columns=False,
    sum_lists=False,
    aggregate_telemetry=False,
) -> pd.DataFrame:
    """Clean the dataframe.

    :param sum_lists:
    :param keep_task_id:
    :param keep_only_nans_columns:
    :param keep_non_numeric_columns:
    :param df:
    :param logger:
    :param keep_telemetry_percent_columns:
    :param aggregate_telemetry: We use some very simplistic forms of aggregations just
      to reduce the complexity of the dataframe. Use this feature very carefully as the
      aggregation may be misleading.
    :return:
    """
    has_telemetry_diff_columns = any(col.startswith("telemetry_diff") for col in df.columns)

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
    if keep_task_id:
        task_ids = dfa["task_id"]

    if sum_lists:
        # Identify the original columns that were lists or lists of lists
        list_cols = [
            col for col in dfa.columns if any(isinstance(val, (list, list)) for val in dfa[col])
        ]

        cols_to_drop = []
        # Apply the function to all columns and create new scalar columns
        for col in list_cols:
            try:
                if "telemetry_diff" in col:
                    continue
                dfa[f"{col}_sum"] = dfa[col].apply(flatten_list_with_sum)
                cols_to_drop.append(col)
            except Exception as e:
                logger.exception(e)
        # Apply the function to all columns and create new scalar columns

        # Drop the original columns that were lists or lists of lists
        dfa = dfa.drop(columns=cols_to_drop)

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

        network_cols = [col for col in dfa.columns if col.startswith("telemetry_diff.network")]
        dfa["telemetry_diff.network.activity"] = dfa[network_cols].mean(axis=1)

        io_sum_cols = [col for col in dfa.columns if "disk.io_sum" in col]
        dfa["telemetry_diff.disk.activity"] = dfa[io_sum_cols].mean(axis=1)

        processes_nums_cols = [col for col in dfa.columns if "telemetry_diff.process.num_" in col]
        dfa["telemetry_diff.process.activity"] = dfa[processes_nums_cols].sum(axis=1)

        cols_to_drop.extend(processes_nums_cols)
        cols_to_drop.extend(network_cols)
        cols_to_drop.extend(io_sum_cols)

        cols_to_drop.extend([col for col in dfa.columns if "disk.io_per_disk" in col])

        dfa.drop(columns=cols_to_drop, inplace=True)

    # Removing any leftover cols
    cols_to_drop = [
        col for col in dfa.columns if "telemetry_at_start" in col or "telemetry_at_end" in col
    ]
    if len(cols_to_drop):
        dfa.drop(columns=cols_to_drop, inplace=True)

    if keep_task_id:
        dfa["task_id"] = task_ids

    logmsg = f"Number of columns later: {len(dfa.columns)}"
    if logger:
        logger.info(logmsg)
    else:
        print(logmsg)
    return dfa


def analyze_correlations(df, method="kendall", threshold=0):
    """Analyze correlations."""
    # Create a mask to select the upper triangle of the correlation matrix
    correlation_matrix = df.corr(method=method, numeric_only=True)
    mask = correlation_matrix.where(np.triu(np.ones(correlation_matrix.shape), k=1).astype(bool))
    corrs = []

    # Iterate through the selected upper triangle of the correlation matrix
    for i in range(len(mask.columns)):
        for j in range(i + 1, len(mask.columns)):
            pair = (mask.columns[i], mask.columns[j])
            corr = mask.iloc[i, j]  # Get correlation value
            if abs(corr) >= threshold and pair[0] != pair[1]:
                corrs.append((mask.columns[i], mask.columns[j], round(corr, 2)))

    return pd.DataFrame(
        corrs,
        columns=_CORRELATION_DF_HEADER,
    )


def analyze_correlations_between(
    df: pd.DataFrame,
    col_pattern1,
    col_pattern2,
    method="kendall",
    threshold=0,
):
    """Analyze correlations."""
    corr_df = analyze_correlations(df, method, threshold)
    filtered_df = corr_df[
        (
            corr_df[_CORRELATION_DF_HEADER[0]].str.match(col_pattern1)
            & corr_df[_CORRELATION_DF_HEADER[1]].str.match(col_pattern2)
        )
        | (
            corr_df[_CORRELATION_DF_HEADER[0]].str.match(col_pattern2)
            & corr_df[_CORRELATION_DF_HEADER[1]].str.match(col_pattern1)
        )
    ]
    return filtered_df


def analyze_correlations_used_vs_generated(df: pd.DataFrame, method="kendall", threshold=0):
    """Analyze correlations."""
    return analyze_correlations_between(
        df,
        col_pattern1="used[.]",
        col_pattern2="generated[.]",
        method=method,
        threshold=threshold,
    )


def analyze_correlations_used_vs_telemetry_diff(df: pd.DataFrame, method="kendall", threshold=0):
    """Analyze correlations."""
    return analyze_correlations_between(
        df,
        col_pattern1="^used[.]*",
        col_pattern2="^telemetry_diff[.]*",
        method=method,
        threshold=threshold,
    )


def analyze_correlations_generated_vs_telemetry_diff(
    df: pd.DataFrame, method="kendall", threshold=0
):
    """Analyze correlations."""
    return analyze_correlations_between(
        df,
        col_pattern1="^generated[.]*",
        col_pattern2="^telemetry_diff[.]*",
        method=method,
        threshold=threshold,
    )


def format_number(num):
    """Format a number."""
    suffixes = ["", "K", "M", "B", "T"]
    idx = 0
    while abs(num) >= 1000 and idx < len(suffixes) - 1:
        idx += 1
        num /= 1000.0
    formatted = f"{num:.2f}" if num % 1 != 0 else f"{int(num)}"
    formatted = formatted.rstrip("0").rstrip(".") if "." in formatted else formatted.rstrip(".")
    return f"{formatted}{suffixes[idx]}"


def describe_col(df, col, label=None):
    """Describe a column."""
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
    """Describe columns."""
    return pd.DataFrame(
        [describe_col(df, col, col_label) for col, col_label in zip(cols, col_labels)]
    )


def identify_pareto(df):
    """Identify pareto."""
    datav = df.values
    pareto = []
    for i, point in enumerate(datav):
        if all(np.any(point <= other_point) for other_point in datav[:i]):
            pareto.append(point)
    return pd.DataFrame(pareto, columns=df.columns)


def find_outliers_zscore(row, threshold=3):
    """Find outliers."""
    numeric_columns = [col for col, val in row.items() if pd.api.types.is_numeric_dtype(type(val))]
    z_scores = np.abs(
        (row[numeric_columns] - row[numeric_columns].mean()) / row[numeric_columns].std()
    )
    outliers_columns = list(z_scores[z_scores > threshold].index)
    return outliers_columns
