/** Thin ECharts wrapper with theme defaults and auto-resize. */

import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart, ScatterChart, CustomChart, HeatmapChart } from "echarts/charts";
import {
  DatasetComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption, ECharts } from "echarts/core";

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  CustomChart,
  HeatmapChart,
  DatasetComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  CanvasRenderer,
]);

const THEME_DEFAULTS: EChartsCoreOption = {
  backgroundColor: "transparent",
  textStyle: { color: "#8b93a7", fontSize: 11 },
  color: ["#4f8cff", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#22d3ee", "#fb923c"],
};

interface Props {
  option: EChartsCoreOption;
  height?: number | string;
  onClick?: (params: { data?: unknown; name?: string }) => void;
  className?: string;
}

export function EChart({ option, height = 280, onClick, className }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption({ ...THEME_DEFAULTS, ...option }, { notMerge: true });
  }, [option]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onClick) return;
    chart.on("click", onClick);
    return () => {
      chart.off("click");
    };
  }, [onClick]);

  return <div ref={ref} className={className} style={{ height, width: "100%" }} />;
}
