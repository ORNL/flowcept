/** Inspector panel state — selected entity to show in the right panel. */

import { create } from "zustand";
import type { BlobObjectDoc } from "../api/types";

export interface GraphInspectorDoc extends Record<string, unknown> {
  label: string;
  stats: Record<string, unknown>;
}

export type InspectorEntity =
  | { kind: "object"; data: BlobObjectDoc }
  | { kind: "task" | "activity" | "dataflow"; data: GraphInspectorDoc }
  | null;

interface InspectorState {
  entity: InspectorEntity;
  set: (entity: InspectorEntity) => void;
  clear: () => void;
}

export const useInspectorStore = create<InspectorState>((set) => ({
  entity: null,
  set: (entity) => set({ entity }),
  clear: () => set({ entity: null }),
}));
