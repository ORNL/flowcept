/** Map resolved card rows + viz spec to an ECharts option. */

import type { EChartsCoreOption } from "echarts/core";
import { toEpochSec, type TimeValue } from "../../lib/format";
import { metricKey, type Chart } from "./spec";

const AXIS_STYLE = {
  axisLine: { lineStyle: { color: "#232a3b" } },
  splitLine: { lineStyle: { color: "#181d2a" } },
};

export function specToOption(card: Chart, rows: Record<string, unknown>[]): EChartsCoreOption {
  const viz = card.viz ?? { kind: "bar", stacked: false };
  const data = card.data;

  // Grouped/aggregated data: category axis = group_by, one series per metric.
  if (data?.group_by || data?.metrics?.length) {
    const dim = data?.group_by ?? "group";
    const metrics = data?.metrics?.length ? data.metrics : [{ field: "", agg: "count" as const }];
    const categories = rows.map((r) => String(r[dim] ?? "—"));

    if (viz.kind === "pie") {
      return {
        tooltip: { trigger: "item" },
        series: [
          {
            type: "pie",
            radius: ["35%", "70%"],
            label: { color: "#8b93a7", fontSize: 11 },
            data: rows.map((r) => ({ name: String(r[dim] ?? "—"), value: r[metricKey(metrics[0])] as number })),
          },
        ],
      };
    }

    return {
      grid: { left: 50, right: 12, top: 28, bottom: 40 },
      legend: metrics.length > 1 ? { textStyle: { color: "#8b93a7" } } : undefined,
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: categories, ...AXIS_STYLE, axisLabel: { rotate: categories.some((c) => c.length > 10) ? 30 : 0 } },
      yAxis: { type: "value", ...AXIS_STYLE },
      series: metrics.map((m) => ({
        name: metricKey(m),
        type: viz.kind === "scatter" ? "scatter" : viz.kind === "line" || viz.kind === "area" ? "line" : "bar",
        areaStyle: viz.kind === "area" ? {} : undefined,
        stack: viz.stacked ? "total" : undefined,
        data: rows.map((r) => r[metricKey(m)] as number),
      })),
    };
  }

  // x/y timeseries data.
  if (data?.x && data?.y?.length) {
    const x = data.x;
    return {
      grid: { left: 56, right: 12, top: 28, bottom: 32 },
      legend: data.y.length > 1 ? { textStyle: { color: "#8b93a7" } } : undefined,
      tooltip: { trigger: "axis" },
      xAxis: { type: "time", ...AXIS_STYLE },
      yAxis: { type: "value", ...AXIS_STYLE },
      series: data.y.map((field) => ({
        name: field.split(".").at(-1),
        type: viz.kind === "scatter" ? "scatter" : viz.kind === "bar" ? "bar" : "line",
        areaStyle: viz.kind === "area" ? {} : undefined,
        showSymbol: viz.kind === "scatter",
        data: rows
          .filter((r) => r[field] !== null && r[field] !== undefined && toEpochSec(r[x] as TimeValue) !== null)
          .map((r) => [(toEpochSec(r[x] as TimeValue) as number) * 1000, r[field] as number]),
      })),
    };
  }

  return { title: { text: "No data binding", textStyle: { color: "#8b93a7", fontSize: 12 } } };
}
