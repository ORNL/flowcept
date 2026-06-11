/** Inspector panel state — selected entity to show in the right panel. */

import { create } from "zustand";
import type { BlobObjectDoc } from "../api/types";

export type InspectorEntity = { kind: "object"; data: BlobObjectDoc } | null;

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
