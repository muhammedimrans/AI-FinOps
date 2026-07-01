import { create } from "zustand";

export type ToastVariant = "success" | "error" | "warning" | "info";

export interface Toast {
  id: string;
  variant: ToastVariant;
  title: string;
  description?: string;
  duration: number;
}

interface ToastState {
  toasts: Toast[];
  dismiss: (id: string) => void;
}

const DEFAULT_DURATION = 5000;

export const useToastStore = create<ToastState>()((set) => ({
  toasts: [],
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

function push(variant: ToastVariant, title: string, description?: string, duration = DEFAULT_DURATION) {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const newToast: Toast = { id, variant, title, duration, ...(description ? { description } : {}) };
  useToastStore.setState((s) => ({ toasts: [...s.toasts, newToast] }));
  return id;
}

/**
 * Fire-and-forget toast API — call from anywhere, no provider/hook needed.
 * Rendered by <ToastContainer /> mounted once in AppLayout.
 */
export const toast = {
  success: (title: string, description?: string) => push("success", title, description),
  error: (title: string, description?: string) => push("error", title, description),
  warning: (title: string, description?: string) => push("warning", title, description),
  info: (title: string, description?: string) => push("info", title, description),
};
