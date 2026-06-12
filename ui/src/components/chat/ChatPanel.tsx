/** Provenance chat panel: streams /api/v1/chat SSE events into rich message parts. */

import { useEffect, useRef, useState } from "react";
import { useRouterState } from "@tanstack/react-router";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { Bot, ChevronDown, Eraser, Send, Wrench } from "lucide-react";
import type { PanelImperativeHandle } from "react-resizable-panels";
import { API_BASE } from "../../api/client";
import { useChatStore, type ChatMsg } from "../../stores/chatStore";
import { useHighlightStore } from "../../stores/highlightStore";
import { EChart } from "../charts/EChart";
import { Markdown } from "../markdown/Markdown";
import { specToOption } from "../dashboard/specToOption";

function contextHint(pathname: string): string {
  const wf = pathname.match(/\/workflows\/([^/?]+)/);
  if (wf) return `Queries are scoped to this workflow execution (id: ${decodeURIComponent(wf[1])}).`;
  const camp = pathname.match(/\/campaigns\/([^/?]+)/);
  if (camp) return `Queries are scoped to this campaign (id: ${decodeURIComponent(camp[1])}).`;
  return "Queries are scoped to the page you're viewing.";
}

function routeContext(pathname: string): Record<string, string> {
  const wf = pathname.match(/\/workflows\/([^/?]+)/);
  if (wf) return { workflow_id: decodeURIComponent(wf[1]) };
  const camp = pathname.match(/\/campaigns\/([^/?]+)/);
  if (camp) return { campaign_id: decodeURIComponent(camp[1]) };
  const dash = pathname.match(/\/dashboards\/([^/?]+)/);
  if (dash) return { dashboard_id: decodeURIComponent(dash[1]) };
  return {};
}

interface ChatPanelProps {
  panelHandle?: PanelImperativeHandle | null;
}

export function ChatPanel({ panelHandle }: ChatPanelProps) {
  const { busy, messages, setBusy, push, appendPart, reset } = useChatStore();
  const [input, setInput] = useState("");
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    const history = [...messages, { role: "user", parts: [{ kind: "text", text }] } as ChatMsg];
    push({ role: "user", parts: [{ kind: "text", text }] });
    setBusy(true);

    const apiMessages = history.map((m) => ({
      role: m.role,
      content: m.parts
        .filter((p) => p.kind === "text")
        .map((p) => (p.kind === "text" ? p.text : ""))
        .join("\n"),
    }));

    try {
      await fetchEventSource(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: apiMessages,
          context: routeContext(pathname),
          stream: true,
          allow_dashboard_edit: pathname.startsWith("/dashboards/"),
        }),
        openWhenHidden: true,
        onmessage(msg) {
          if (!msg.event) return;
          const data = msg.data ? JSON.parse(msg.data) : null;
          if (msg.event === "token" && data) appendPart({ kind: "text", text: String(data) });
          if (msg.event === "tool_call" && data) appendPart({ kind: "tool", name: data.name, args: data.args });
          if (msg.event === "card" && data?.chart) appendPart({ kind: "chart", data });
          if (msg.event === "ui:highlight" && Array.isArray(data?.task_ids)) {
            useHighlightStore.getState().setHighlight(data.task_ids as string[]);
            appendPart({ kind: "ui_highlight", task_ids: data.task_ids as string[] });
          }
          if (msg.event === "error" && data) appendPart({ kind: "text", text: `⚠️ ${data}` });
        },
        onerror(err) {
          appendPart({ kind: "text", text: `⚠️ Chat request failed: ${err}` });
          throw err; // stop retrying
        },
      });
    } catch {
      /* error already surfaced in the transcript */
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col border-t border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="flex items-center gap-1.5 text-sm font-medium"><Bot size={15} /> Flowcept Agent</span>
        <div className="flex items-center gap-2">
          <button onClick={reset} title="Clear conversation" className="text-fg-muted hover:text-fg">
            <Eraser size={14} />
          </button>
          <button
            onClick={() => panelHandle?.collapse()}
            title="Minimize chat"
            className="text-fg-muted hover:text-fg"
          >
            <ChevronDown size={15} />
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-3">
        {messages.length === 0 && (
          <div className="text-fg-muted px-2 py-8 text-center text-xs">
            Ask about your provenance data — e.g. "how many tasks failed?", "plot task durations per
            activity". {contextHint(pathname)}
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={msg.role === "user" ? "flex justify-end" : ""}>
            <div
              className={
                msg.role === "user"
                  ? "bg-accent-soft max-w-[85%] rounded-lg px-3 py-2 text-xs"
                  : "max-w-full space-y-2 text-xs"
              }
            >
              {msg.parts.map((part, j) => {
                if (part.kind === "text") return <Markdown key={j}>{part.text}</Markdown>;
                if (part.kind === "ui_highlight")
                  return (
                    <div key={j} className="border-accent/40 text-accent bg-accent-soft flex items-center gap-1.5 rounded border px-2.5 py-1.5 text-[11px]">
                      <span>↗</span>
                      <span>
                        Highlighted {part.task_ids.length} task{part.task_ids.length !== 1 ? "s" : ""} in the Dataflow graph.
                        {" "}
                        <button
                          onClick={() => useHighlightStore.getState().clearHighlight()}
                          className="underline opacity-70 hover:opacity-100"
                        >
                          Clear
                        </button>
                      </span>
                    </div>
                  );
                if (part.kind === "tool")
                  return (
                    <details key={j} className="text-fg-muted">
                      <summary className="flex cursor-pointer items-center gap-1.5 text-[11px]">
                        <Wrench size={11} /> ran {part.name}
                      </summary>
                      <pre className="card mt-1 overflow-x-auto p-2 text-[10px]">
                        {JSON.stringify(part.args, null, 2)}
                      </pre>
                    </details>
                  );
                return (
                  <div key={j} className="card p-2">
                    <div className="text-fg-muted mb-1 text-[11px]">{part.data.chart.title || "chart"}</div>
                    <EChart option={specToOption(part.data.chart, part.data.rows)} height={200} />
                  </div>
                );
              })}
            </div>
          </div>
        ))}
        {busy && <div className="text-fg-muted animate-pulse px-2 text-xs">thinking…</div>}
      </div>

      <div className="border-t border-border p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            rows={2}
            placeholder="Ask about your workflows… (Enter to send)"
            className="bg-surface-2 flex-1 resize-none rounded-md border border-border px-2.5 py-2 text-xs outline-none focus:border-accent"
          />
          <button
            onClick={() => void send()}
            disabled={busy || !input.trim()}
            className="bg-accent-soft border-accent/40 rounded-md border p-2 disabled:opacity-40"
          >
            <Send size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
