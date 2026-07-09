/** Task timeline (gantt) rendered with an ECharts custom series. */

import { useMemo } from "react";
import type { Task } from "../../api/types";
import { statusColor, fmtDuration, fmtTs, toEpochSec } from "../../lib/format";
import { EChart } from "./EChart";

const MAX_BARS = 5000;

interface Props {
  tasks: Task[];
  onTaskClick?: (taskId: string) => void;
}

export function GanttChart({ tasks, onTaskClick }: Props) {
  const { option, truncated } = useMemo(() => {
    const usable = tasks
      .map((t) => ({ t, start: toEpochSec(t.started_at), end: toEpochSec(t.ended_at) }))
      .filter((r) => r.start !== null)
      .sort((a, b) => (a.start ?? 0) - (b.start ?? 0));
    const sliced = usable.slice(0, MAX_BARS);
    const now = Date.now() / 1000;
    const rows = sliced.map(({ t, start, end }, i) => ({
      value: [i, (start as number) * 1000, (end ?? now) * 1000],
      itemStyle: { color: statusColor(t.status) },
      task: t,
    }));
    const opt = {
      grid: { left: 8, right: 16, top: 8, bottom: 40, containLabel: false },
      xAxis: {
        type: "time" as const,
        axisLine: { lineStyle: { color: "#232a3b" } },
        splitLine: { lineStyle: { color: "#181d2a" } },
      },
      yAxis: { type: "value" as const, min: -1, max: Math.max(rows.length, 5), show: false, inverse: true },
      dataZoom: [
        { type: "inside" as const, filterMode: "weakFilter" as const },
        { type: "slider" as const, height: 18, bottom: 8, borderColor: "#232a3b" },
      ],
      tooltip: {
        formatter: (p: { data?: { task?: Task } }) => {
          const t = p.data?.task;
          if (!t) return "";
          const start = toEpochSec(t.started_at);
          const end = toEpochSec(t.ended_at);
          const dur = start !== null && end !== null ? fmtDuration(end - start) : "running";
          return [
            `<b>${t.activity_id ?? t.task_id}</b>`,
            `status: ${t.status ?? "?"}`,
            `start: ${fmtTs(t.started_at)}`,
            `duration: ${dur}`,
          ].join("<br/>");
        },
      },
      series: [
        {
          type: "custom" as const,
          encode: { x: [1, 2], y: 0 },
          data: rows,
          renderItem: (
            _params: unknown,
            api: {
              value: (i: number) => number;
              coord: (v: number[]) => number[];
              style: () => Record<string, unknown>;
            },
          ) => {
            const idx = api.value(0);
            const start = api.coord([api.value(1), idx]);
            const end = api.coord([api.value(2), idx]);
            const h = 6;
            return {
              type: "rect",
              shape: { x: start[0], y: start[1] - h / 2, width: Math.max(end[0] - start[0], 2), height: h },
              style: api.style(),
            };
          },
        },
      ],
    };
    return { option: opt, truncated: usable.length > MAX_BARS };
  }, [tasks]);

  return (
    <div>
      {truncated && <div className="text-fg-muted text-xs mb-1">Showing first {MAX_BARS} tasks.</div>}
      <EChart
        option={option}
        height={Math.min(Math.max(tasks.length * 9 + 90, 160), 520)}
        onClick={(p) => {
          const task = (p as { data?: { task?: Task } }).data?.task;
          if (task && onTaskClick) onTaskClick(task.task_id);
        }}
      />
    </div>
  );
}
