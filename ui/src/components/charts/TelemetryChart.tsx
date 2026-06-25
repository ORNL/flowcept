/** Telemetry timeseries: combined normalized chart + individual line plots. */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiPost } from "../../api/client";
import { toEpochSec, type TimeValue } from "../../lib/format";
import { EChart } from "./EChart";

const METRICS: Record<string, string> = {
  "CPU %": "telemetry_at_end.cpu.percent_all",
  "Memory used": "telemetry_at_end.memory.virtual.used",
  "Process CPU %": "telemetry_at_end.process.cpu_percent",
  "Process memory %": "telemetry_at_end.process.memory_percent",
  "Disk read bytes": "telemetry_at_end.disk.io.read_bytes",
  "Net bytes sent": "telemetry_at_end.network.netio.bytes_sent",
};

const METRIC_KEYS = Object.keys(METRICS);
const ALL_FIELDS = Object.values(METRICS);

const AXIS_STYLE = {
  axisLine: { lineStyle: { color: "#232a3b" } },
  splitLine: { lineStyle: { color: "#181d2a" } },
};

function normalize(vals: number[]): number[] {
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  if (max === min) return vals.map(() => 0.5);
  return vals.map((v) => (v - min) / (max - min));
}

export function TelemetryChart({ filter }: { filter: Record<string, unknown> }) {
  const [visibleMetrics, setVisibleMetrics] = useState<Set<string>>(new Set(METRIC_KEYS));
  const [selectedMetric, setSelectedMetric] = useState<string>(METRIC_KEYS[0]);

  const { data: allData, isLoading: allLoading } = useQuery({
    queryKey: ["telemetry-all", filter],
    queryFn: () =>
      apiPost<{ rows: Record<string, unknown>[]; count: number }>("/stats/timeseries", {
        filter,
        fields: ALL_FIELDS,
        x: "started_at",
        limit: 2000,
      }),
  });

  const field = METRICS[selectedMetric];
  const { data: singleData, isLoading: singleLoading } = useQuery({
    queryKey: ["timeseries", filter, field],
    queryFn: () =>
      apiPost<{ rows: Record<string, unknown>[]; count: number }>("/stats/timeseries", {
        filter,
        fields: [field],
        x: "started_at",
        limit: 2000,
      }),
  });

  const anyData = (allData?.rows ?? []).some((r) =>
    ALL_FIELDS.some((f) => r[f] !== null && r[f] !== undefined),
  );

  const combinedOption = useMemo(() => {
    const rows = allData?.rows ?? [];
    const series = METRIC_KEYS.filter((m) => visibleMetrics.has(m)).map((m) => {
      const f = METRICS[m];
      const pts = rows
        .filter((r) => r[f] !== null && r[f] !== undefined)
        .map((r) => ({ x: (toEpochSec(r["started_at"] as TimeValue) ?? 0) * 1000, y: r[f] as number }))
        .filter((p) => p.x !== 0)
        .sort((a, b) => a.x - b.x);
      const normed = normalize(pts.map((p) => p.y));
      return {
        name: m,
        type: "line" as const,
        showSymbol: false,
        data: pts.map((p, i) => [p.x, normed[i]]),
      };
    });
    return {
      grid: { left: 50, right: 16, top: 28, bottom: 40 },
      legend: { textStyle: { color: "#8b93a7" }, bottom: 0, type: "scroll" as const },
      tooltip: {
        trigger: "axis" as const,
        formatter: (params: { seriesName: string; value: [number, number] }[]) =>
          params.map((p) => `${p.seriesName}: ${p.value[1].toFixed(3)}`).join("<br/>"),
      },
      xAxis: { type: "time" as const, ...AXIS_STYLE },
      yAxis: {
        type: "value" as const,
        min: 0,
        max: 1,
        ...AXIS_STYLE,
        axisLabel: { formatter: (v: number) => v.toFixed(1) },
      },
      series,
    };
  }, [allData, visibleMetrics]);

  const singleOption = useMemo(() => {
    const rows = (singleData?.rows ?? []).filter((r) => r[field] !== null && r[field] !== undefined);
    const pts = rows
      .map((r) => [(toEpochSec(r["started_at"] as TimeValue) ?? 0) * 1000, r[field] as number] as [number, number])
      .filter((d) => d[0] !== 0)
      .sort((a, b) => a[0] - b[0]);
    return {
      grid: { left: 60, right: 16, top: 16, bottom: 28 },
      tooltip: { trigger: "axis" as const },
      xAxis: { type: "time" as const, ...AXIS_STYLE },
      yAxis: { type: "value" as const, ...AXIS_STYLE },
      series: [{ name: selectedMetric, type: "line" as const, showSymbol: false, data: pts }],
    };
  }, [singleData, field, selectedMetric]);

  const toggleMetric = (m: string) =>
    setVisibleMetrics((prev) => {
      const next = new Set(prev);
      next.has(m) ? next.delete(m) : next.add(m);
      return next;
    });

  return (
    <div className="space-y-5">
      {/* Combined normalized chart */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium">All metrics (normalized 0–1)</span>
          <div className="flex gap-3">
            <button
              onClick={() => setVisibleMetrics(new Set(METRIC_KEYS))}
              className="text-fg-muted hover:text-fg text-[11px]"
            >
              Show all
            </button>
            <button
              onClick={() => setVisibleMetrics(new Set())}
              className="text-fg-muted hover:text-fg text-[11px]"
            >
              Hide all
            </button>
          </div>
        </div>
        <div className="mb-2 flex flex-wrap gap-1.5">
          {METRIC_KEYS.map((m) => (
            <button
              key={m}
              onClick={() => toggleMetric(m)}
              className={`rounded-full border px-2.5 py-0.5 text-xs ${
                visibleMetrics.has(m)
                  ? "border-accent bg-accent-soft text-fg"
                  : "border-border text-fg-muted hover:text-fg"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
        {allLoading ? (
          <div className="text-fg-muted py-8 text-center text-xs">Loading…</div>
        ) : anyData ? (
          <EChart option={combinedOption} height={240} />
        ) : (allData?.rows?.length ?? 0) === 0 ? (
          <div className="text-fg-muted py-8 text-center text-xs">
            No tasks matched this filter.
          </div>
        ) : (
          <div className="text-fg-muted py-8 text-center text-xs">
            Tasks were found but no telemetry values are present.
            Ensure <code className="text-xs">telemetry_capture.enable: true</code> in your Flowcept settings.
          </div>
        )}
      </div>

      {/* Individual metric detail */}
      {anyData && (
        <div>
          <div className="mb-2 text-xs font-medium">Individual metric</div>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {METRIC_KEYS.map((m) => (
              <button
                key={m}
                onClick={() => setSelectedMetric(m)}
                className={`rounded-full border px-2.5 py-0.5 text-xs ${
                  m === selectedMetric
                    ? "border-accent bg-accent-soft text-fg"
                    : "border-border text-fg-muted hover:text-fg"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          {singleLoading ? (
            <div className="text-fg-muted py-4 text-center text-xs">Loading…</div>
          ) : (
            <EChart option={singleOption} height={200} />
          )}
        </div>
      )}
    </div>
  );
}
