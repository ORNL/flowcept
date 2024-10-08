"""Plot module."""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import plotly.graph_objs as go

from flowcept.analytics.analytics_utils import format_number, identify_pareto


def heatmap(df: pd.DataFrame, method="kendall", figsize=(13, 10), heatmap_args={}):
    """Heat map plot.

    :param figsize:
    :param heatmap_args: Any other argument for the heatmap.
    :param df: dataframe to plot the heatmap
    :param method: Possible values: 'kendall', 'spearman', 'pearson'
    :return:
    """
    correlation_matrix = df.corr(method=method)
    plt.figure(figsize=figsize)
    sns.heatmap(
        correlation_matrix,
        annot=False,
        cmap="coolwarm",
        fmt=".1f",
        vmin=-1,
        vmax=1,
        **heatmap_args,
    )


# TODO: :idea: consider finding xcol, ycol, color_col automatically based on high
#  correlations for eg
def scatter2d_with_colors(
    df,
    x_col,
    y_col,
    color_col,
    x_label=None,
    y_label=None,
    color_label=None,
    xaxis_title=None,
    yaxis_title=None,
    plot_horizon_line=True,
    horizon_quantile=0.5,
    plot_pareto=True,
):
    """Scatter 2D plot with colors."""
    x_label = x_col if x_label is None else x_label
    y_label = y_col if y_label is None else y_label
    color_label = color_col if color_label is None else color_label

    hovertemplate = (
        x_label
        + ": %{customdata[0]}<br>"
        + y_label
        + ": %{customdata[1]}<br>"
        + color_label
        + ": %{customdata[2]}"
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df[x_col],
            y=df[y_col],
            mode="markers",
            name="",
            customdata=df[[x_col, y_col, color_col]].applymap(format_number),
            hovertemplate=hovertemplate,
            marker=dict(
                color=df[color_col],
                opacity=0.8,
                reversescale=False,
                colorscale="reds",
                colorbar=dict(orientation="v", title=color_label),
                size=5,
            ),
        )
    )

    if plot_horizon_line:
        k = df[y_col].quantile(horizon_quantile)
        y_line = np.linspace(df[x_col].min(), df[x_col].max(), len(df) * 100)
        fig.add_trace(
            go.Scatter(
                x=y_line,
                y=[k] * len(y_line),
                mode="markers",
                marker=dict(size=1, color="darkred", opacity=0.5),
                name="",
            )
        )

    if plot_pareto:
        pareto_front = identify_pareto(df[[x_col, y_col]])
        fig.add_trace(
            go.Scatter(
                x=pareto_front[x_col],
                y=pareto_front[y_col],
                mode="markers",
                marker=dict(size=10, color="blue"),
                name="Pareto Front",
            )
        )

    fig.update_layout(xaxis_title=xaxis_title, yaxis_title=yaxis_title)
    fig.show()
