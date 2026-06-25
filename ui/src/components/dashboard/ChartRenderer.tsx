/** Renders one dashboard chart by type; chart/metric/table charts resolve data via /stats/chart_data. */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiPost } from "../../api/client";
import type { ChartDataResult } from "../../api/types";
import { useInspectorStore } from "../../stores/inspectorStore";
import { EChart } from "../charts/EChart";
import { Markdown } from "../markdown/Markdown";
import { metricKey, type Chart, type DashboardSpec } from "./spec";
import { specToOption } from "./specToOption";

function useChartData(chart: Chart, context: Record<string, unknown>, live: boolean) {
  return useQuery({
    queryKey: ["chartData", chart.data, context],
    queryFn: () => apiPost<ChartDataResult>("/stats/chart_data", { data: chart.data, context }),
    enabled: chart.data != null,
    refetchInterval: live ? (chart.refresh_interval_sec ?? 5) * 1000 : false,
  });
}

function DataChart({ chart, context }: { chart: Chart; context: Record<string, unknown> }) {
  const { data, isLoading, error } = useChartData(chart, context, chart.live);
  const setInspector = useInspectorStore((s) => s.set);

  const option = useMemo(() => specToOption(chart, data?.rows ?? []), [chart, data]);
  const rows = data?.rows ?? [];

  function openInspector() {
    if (rows.length > 0) setInspector({ kind: "chart", title: chart.title || chart.chart_id, rows });
  }

  if (isLoading) return <div className="text-fg-muted p-4 text-xs">Loading…</div>;
  if (error) return <div className="text-err p-4 text-xs">{String(error)}</div>;

  if (chart.type === "metric") {
    const metric = chart.data?.metrics?.[0];
    const value = metric ? rows[0]?.[metricKey(metric)] : rows.length;
    const display = typeof value === "number" ? (Number.isInteger(value) ? value : value.toFixed(3)) : String(value ?? "—");
    return (
      <div className="flex h-full flex-col items-center justify-center cursor-pointer" onClick={openInspector}>
        <div className="text-3xl font-semibold">{display}</div>
        {metric && <div className="text-fg-muted mt-1 text-xs">{metricKey(metric)}</div>}
      </div>
    );
  }

  if (chart.type === "table") {
    const cols = rows.length ? Object.keys(rows[0]) : [];
    return (
      <div className="h-full overflow-auto px-2 pb-2">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-fg-muted sticky top-0 bg-surface text-left">
              {cols.map((c) => (
                <th key={c} className="border-b border-border px-2 py-1.5 font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 200).map((r, i) => (
              <tr key={i} className="border-b border-border/40">
                {cols.map((c) => (
                  <td key={c} className="max-w-48 overflow-hidden text-ellipsis whitespace-nowrap px-2 py-1">
                    {r[c] === null || r[c] === undefined ? "—" : String(r[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return <div className="h-full cursor-pointer" onClick={openInspector}><EChart option={option} height="100%" /></div>;
}

export function ChartRenderer({ chart, spec }: { chart: Chart; spec: DashboardSpec }) {
  if (chart.type === "markdown") {
    return (
      <div className="h-full overflow-auto p-3">
        <Markdown>{chart.content ?? ""}</Markdown>
      </div>
    );
  }
  return <DataChart chart={chart} context={spec.context} />;
}
