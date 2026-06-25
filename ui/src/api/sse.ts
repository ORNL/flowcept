/** SSE hook for the /api/v1/stream endpoints: cursor resume, backoff reconnect, tab-pause. */

import { useEffect, useRef } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { API_BASE } from "./client";

interface StreamOptions<T> {
  path: string; // e.g. "/stream/tasks"
  params: Record<string, string | undefined>;
  event: string; // e.g. "tasks"
  enabled: boolean;
  onBatch: (docs: T[], cursor: number) => void;
}

export function useEventStream<T>({ path, params, event, enabled, onBatch }: StreamOptions<T>) {
  const cursorRef = useRef<number>(0);
  const onBatchRef = useRef(onBatch);
  onBatchRef.current = onBatch;
  const paramsKey = JSON.stringify(params);

  useEffect(() => {
    if (!enabled) return;
    const ctrl = new AbortController();
    let retryMs = 1000;

    const connect = () => {
      const url = new URL(API_BASE + path, window.location.origin);
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined) url.searchParams.set(k, v);
      }
      if (cursorRef.current > 0) url.searchParams.set("since", String(cursorRef.current));

      void fetchEventSource(url.toString(), {
        signal: ctrl.signal,
        openWhenHidden: false, // pause when tab hidden; resumes from cursor on visible
        onmessage(msg) {
          if (msg.event !== event || !msg.data) return;
          try {
            const payload = JSON.parse(msg.data) as Record<string, unknown>;
            const docs = (payload[event] as T[]) ?? [];
            const cursor = (payload["cursor"] as number) ?? cursorRef.current;
            cursorRef.current = cursor;
            retryMs = 1000;
            if (docs.length) onBatchRef.current(docs, cursor);
          } catch {
            /* ignore malformed events */
          }
        },
        onerror() {
          // Exponential backoff with jitter; fetchEventSource retries after the throw delay.
          retryMs = Math.min(retryMs * 2, 30_000);
          return retryMs + Math.random() * 500;
        },
      });
    };

    connect();
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, paramsKey, event, enabled]);
}
