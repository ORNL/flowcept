/** Telemetry timeseries over tasks with a metric picker, backed by /stats/timeseries. */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiPost } from "../../api/client";
import { fmtTs, toEpochSec, type TimeValue } from "../../lib/format";
import { EChart } from "./EChart";

const METRICS: Record<string, string> = {
  "CPU %": "telemetry_at_end.cpu.percent_all",
  "Memory used": "telemetry_at_end.memory.virtual.used",
  "Process CPU %": "telemetry_at_end.process.cpu_percent",
  "Process memory %": "telemetry_at_end.process.memory_percent",
  "Disk read bytes": "telemetry_at_end.disk.io.read_bytes",
  "Net bytes sent": "telemetry_at_end.network.netio.bytes_sent",
};

export function TelemetryChart({ filter }: { filter: Record<string, unknown> }) {
  const [metric, setMetric] = useState("CPU %");
  const field = METRICS[metric];

  const { data, isLoading } = useQuery({
    queryKey: ["timeseries", filter, field],
    queryFn: () =>
      apiPost<{ rows: Record<string, unknown>[]; count: number }>("/stats/timeseries", {
        filter,
        fields: [field],
        x: "started_at",
        limit: 2000,
      }),
  });

  const option = useMemo(() => {
    const rows = (data?.rows ?? []).filter((r) => r[field] !== null && r[field] !== undefined);
    return {
      grid: { left: 60, right: 16, top: 24, bottom: 28 },
      xAxis: {
        type: "time" as const,
        axisLine: { lineStyle: { color: "#232a3b" } },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value" as const,
        axisLine: { lineStyle: { color: "#232a3b" } },
        splitLine: { lineStyle: { color: "#181d2a" } },
      },
      tooltip: {
        trigger: "item" as const,
        formatter: (p: { data?: [number, number, string] }) =>
          p.data ? `${p.data[2]}<br/>${fmtTs(p.data[0] / 1000)}<br/><b>${p.data[1]}</b>` : "",
      },
      series: [
        {
          type: "scatter" as const,
          symbolSize: 7,
          data: rows
            .map((r) => [
              (toEpochSec(r["started_at"] as TimeValue) ?? 0) * 1000,
              r[field] as number,
              (r["activity_id"] as string) ?? (r["task_id"] as string),
            ])
            .filter((d) => d[0] !== 0),
        },
      ],
    };
  }, [data, field]);

  const hasData = (data?.rows ?? []).some((r) => r[field] !== null && r[field] !== undefined);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {Object.keys(METRICS).map((m) => (
          <button
            key={m}
            onClick={() => setMetric(m)}
            className={`rounded-full border px-2.5 py-0.5 text-xs ${
              m === metric ? "border-accent bg-accent-soft text-fg" : "border-border text-fg-muted hover:text-fg"
            }`}
          >
            {m}
          </button>
        ))}
      </div>
      {isLoading ? (
        <div className="text-fg-muted py-10 text-center text-xs">Loading…</div>
      ) : hasData ? (
        <EChart option={option} height={300} />
      ) : (
        <div className="text-fg-muted py-10 text-center text-xs">
          No telemetry values for this metric (telemetry capture may be disabled).
        </div>
      )}
    </div>
  );
}
