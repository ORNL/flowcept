/** Chat panel state (ephemeral UI state; history is client-held and sent with each request). */

import { create } from "zustand";
import type { Card } from "../components/dashboard/spec";

export interface ChatCardData {
  card: Card;
  rows: Record<string, unknown>[];
  count: number;
}

export type ChatPart =
  | { kind: "text"; text: string }
  | { kind: "card"; data: ChatCardData }
  | { kind: "tool"; name: string; args?: Record<string, unknown> };

export interface ChatMsg {
  role: "user" | "assistant";
  parts: ChatPart[];
}

interface ChatState {
  open: boolean;
  busy: boolean;
  messages: ChatMsg[];
  toggle: () => void;
  setBusy: (busy: boolean) => void;
  push: (msg: ChatMsg) => void;
  appendPart: (part: ChatPart) => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  open: false,
  busy: false,
  messages: [],
  toggle: () => set((s) => ({ open: !s.open })),
  setBusy: (busy) => set({ busy }),
  push: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  appendPart: (part) =>
    set((s) => {
      const messages = [...s.messages];
      const last = messages.at(-1);
      if (last?.role === "assistant") {
        messages[messages.length - 1] = { ...last, parts: [...last.parts, part] };
      } else {
        messages.push({ role: "assistant", parts: [part] });
      }
      return { messages };
    }),
  reset: () => set({ messages: [] }),
}));
