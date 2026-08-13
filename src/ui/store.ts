// Client-side UI state — and nothing else.
//
// This replaces the in-browser "kernel" workspace store, which held a full
// shadow copy of the domain (agents, prompts, tools, telemetry, approvals,
// audit) seeded from ~2,000 lines of demo fixtures. That made sense when the
// console had no backend. It stopped making sense once every module became
// server-backed, and it actively misled: "Reset demo" wrote the fixtures into
// localStorage, after which Home and global search reported invented figures
// that looked exactly like real ones.
//
// What genuinely belongs on the client is here: nav layout, the command
// palette's open state, and transient toasts. Domain state comes from the API.
import { create } from 'zustand';

export type ToastKind = 'info' | 'ok' | 'warn' | 'err';

export interface Toast {
  id: string;
  kind: ToastKind;
  message: string;
}

interface UiStore {
  navCollapsed: boolean;
  searchOpen: boolean;
  toasts: Toast[];
  toggleNav: () => void;
  setSearchOpen: (open: boolean) => void;
  pushToast: (kind: ToastKind, message: string) => void;
  dismissToast: (id: string) => void;
}

let _toastSeq = 0;

export const useUi = create<UiStore>((set) => ({
  navCollapsed: false,
  searchOpen: false,
  toasts: [],

  toggleNav: () => set((s) => ({ navCollapsed: !s.navCollapsed })),
  setSearchOpen: (open) => set({ searchOpen: open }),

  pushToast: (kind, message) =>
    set((s) => ({ toasts: [...s.toasts, { id: `t${++_toastSeq}`, kind, message }] })),
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
