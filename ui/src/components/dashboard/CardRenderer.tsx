/** Renders one dashboard card by type; chart/metric/table cards resolve data via /stats/card_data. */

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiPost } from "../../api/client";
import type { CardDataResult } from "../../api/types";
import { useProvenanceCard } from "../../api/queries";
import { EChart } from "../charts/EChart";
import { Markdown } from "../markdown/Markdown";
import { metricKey, type Card, type DashboardSpec } from "./spec";
import { specToOption } from "./specToOption";

function useCardData(card: Card, context: Record<string, unknown>, live: boolean) {
  return useQuery({
    queryKey: ["cardData", card.data, context],
    queryFn: () => apiPost<CardDataResult>("/stats/card_data", { data: card.data, context }),
    enabled: card.data != null,
    refetchInterval: live ? (card.refresh_interval_sec ?? 5) * 1000 : false,
  });
}

function DataCard({ card, context }: { card: Card; context: Record<string, unknown> }) {
  const { data, isLoading, error } = useCardData(card, context, card.live);

  const option = useMemo(() => specToOption(card, data?.rows ?? []), [card, data]);

  if (isLoading) return <div className="text-fg-muted p-4 text-xs">Loading…</div>;
  if (error) return <div className="text-err p-4 text-xs">{String(error)}</div>;
  const rows = data?.rows ?? [];

  if (card.type === "metric") {
    const metric = card.data?.metrics?.[0];
    const value = metric ? rows[0]?.[metricKey(metric)] : rows.length;
    const display = typeof value === "number" ? (Number.isInteger(value) ? value : value.toFixed(3)) : String(value ?? "—");
    return (
      <div className="flex h-full flex-col items-center justify-center">
        <div className="text-3xl font-semibold">{display}</div>
        {metric && <div className="text-fg-muted mt-1 text-xs">{metricKey(metric)}</div>}
      </div>
    );
  }

  if (card.type === "table") {
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

  return <EChart option={option} height="100%" />;
}

function ProvCardCard({ card }: { card: Card }) {
  const scope = card.workflow_id ? ("workflows" as const) : ("campaigns" as const);
  const id = card.workflow_id ?? card.campaign_id ?? "";
  const cardQuery = useProvenanceCard(scope, id, Boolean(id));
  if (!id) return <div className="text-fg-muted p-4 text-xs">Set workflow_id or campaign_id on this card.</div>;
  if (cardQuery.isLoading) return <div className="text-fg-muted p-4 text-xs">Generating…</div>;
  if (cardQuery.error) return <div className="text-err p-4 text-xs">{String(cardQuery.error)}</div>;
  return (
    <div className="h-full overflow-auto p-3">
      <Markdown>{cardQuery.data ?? ""}</Markdown>
    </div>
  );
}

export function CardRenderer({ card, spec }: { card: Card; spec: DashboardSpec }) {
  if (card.type === "markdown") {
    return (
      <div className="h-full overflow-auto p-3">
        <Markdown>{card.content ?? ""}</Markdown>
      </div>
    );
  }
  if (card.type === "prov_card") return <ProvCardCard card={card} />;
  return <DataCard card={card} context={spec.context} />;
}
