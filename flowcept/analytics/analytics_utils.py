import logging
import numpy as np


def clean_telemetry_dataframe(
    df, logger: logging.Logger = None, drop_percent_cols=True, aggregate=False
):
    """

    :param df:
    :param logger:
    :param drop_percent_cols:
    :param aggregate: We use some very simplistic forms of aggregations just
     to reduce the complexity of the dataframe. Use this feature very carefully as the aggregation may be misleading.
    :return:
    """
    has_telemetry_diff_column = any(
        col.startswith("telemetry_diff") for col in df.columns
    )

    if not has_telemetry_diff_column:
        raise Exception(
            "We assume that the dataframe has telemetry differences."
        )

    logmsg = f"Number of columns originally: {len(df.columns)}"
    if logger:
        logger.info(logmsg)
    else:
        print(logmsg)

    # Get only the columns of interest for analysis
    dfa = df.filter(regex="used|generated|telemetry_diff")

    # Select numeric only columns
    dfa = dfa.select_dtypes(include=np.number)

    # Select non-zero columns only
    dfa = dfa.loc[:, (dfa != 0).any()]

    # Remove duplicate columns
    dfa_T = dfa.T
    dfa = dfa_T.drop_duplicates(keep="first").T

    # used_memory = dfa["telemetry_diff.memory.swap.used"] + dfa["telemetry_diff.memory.virtual.used"]
    # used_memory = -1 * dfa["telemetry_diff.memory.virtual.available"].apply(
    #     int)
    # used_memory = dfa["telemetry_diff.memory.swap.free"]
    # used_memory = dfa["telemetry_diff.memory.virtual.used"]
    # used_memory = df["telemetry_at_end.memory.virtual.active"]
    # used_memory = df["telemetry_at_end.memory.swap.used"]

    # cpu_times = dfa[['telemetry_diff.process.cpu_times.user',
    #                  'telemetry_diff.process.cpu_times.system']]

    cols_to_drop = []

    if drop_percent_cols:
        cols_to_drop.extend([col for col in dfa.columns if "percent" in col])
        dfa.drop(columns=cols_to_drop, inplace=True)

    if aggregate:
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
    dfa.drop(columns=cols_to_drop, inplace=True)

    # cols_to_drop.extend(
    #     [col for col in dfa.columns if "telemetry_diff.memory." in col])
    # cols_to_drop.extend(
    #     [col for col in dfa.columns if "telemetry_diff.process." in col])
    # cols_to_drop.extend([
    #     "telemetry_diff.cpu.times_avg.idle",
    #     "telemetry_diff.disk.disk_usage.free"
    # ])

    # cols_to_keep = {"telemetry_diff.cpu.times_avg.user", "telemetry_diff.cpu.times_avg.system", "telemetry_diff.cpu.times_per_cpu.sum_user", "telemetry_diff.cpu.times_per_cpu.sum_system"}
    # cols_to_drop.extend([col for col in dfa.columns if col not in cols_to_keep])

    # dfa['telemetry_diff.memory.used'] = used_memory
    # # dfa['telemetry_diff.process.memory'] = process_mem_sum

    logmsg = f"Number of columns later: {len(dfa.columns)}"
    if logger:
        logger.info(logmsg)
    else:
        print(logmsg)
    return dfa
