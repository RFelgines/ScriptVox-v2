"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useT } from "@/lib/i18n/LanguageContext";

// Remplace window.confirm / window.alert : boîte de confirmation et notifications éphémères
// dans la direction artistique de l'app (audit 2026-09-25, UX-4/UX-11).

type ToastTone = "info" | "error";

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
  action?: ToastAction;
}

interface ConfirmOptions {
  title: string;
  message?: string;
  confirmLabel?: string;
  danger?: boolean;
}

interface FeedbackContextValue {
  toast: (
    message: string,
    opts?: { tone?: ToastTone; action?: ToastAction; durationMs?: number },
  ) => void;
  confirm: (opts: ConfirmOptions) => Promise<boolean>;
}

const FeedbackContext = createContext<FeedbackContextValue | null>(null);

export function useFeedback(): FeedbackContextValue {
  const ctx = useContext(FeedbackContext);
  if (!ctx) throw new Error("useFeedback must be used inside FeedbackProvider");
  return ctx;
}

export default function FeedbackProvider({ children }: { children: ReactNode }) {
  const t = useT();
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [dialog, setDialog] = useState<ConfirmOptions | null>(null);
  const resolveRef = useRef<((value: boolean) => void) | null>(null);
  const nextId = useRef(1);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback<FeedbackContextValue["toast"]>(
    (message, opts) => {
      const id = nextId.current++;
      setToasts((prev) => [
        ...prev.slice(-3),
        { id, message, tone: opts?.tone ?? "info", action: opts?.action },
      ]);
      window.setTimeout(() => dismiss(id), opts?.durationMs ?? 6000);
    },
    [dismiss],
  );

  const confirm = useCallback<FeedbackContextValue["confirm"]>((opts) => {
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve;
      setDialog(opts);
    });
  }, []);

  function answer(value: boolean) {
    resolveRef.current?.(value);
    resolveRef.current = null;
    setDialog(null);
  }

  // Focus sur « Confirmer » à l'ouverture, Échap = annuler.
  useEffect(() => {
    if (!dialog) return;
    confirmButtonRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        resolveRef.current?.(false);
        resolveRef.current = null;
        setDialog(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dialog]);

  return (
    <FeedbackContext.Provider value={{ toast, confirm }}>
      {children}

      {/* Notifications : au-dessus du lecteur (bas de page), empilées. */}
      <div
        className="pointer-events-none fixed right-4 bottom-28 z-[60] flex max-w-sm flex-col gap-2"
        aria-live="polite"
      >
        {toasts.map((item) => (
          <div
            key={item.id}
            role={item.tone === "error" ? "alert" : "status"}
            className={`pointer-events-auto flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm shadow-lg transition-all duration-200 starting:translate-y-2 starting:opacity-0 ${
              item.tone === "error"
                ? "border-danger/40 bg-surface text-danger"
                : "border-border bg-surface text-foreground"
            }`}
          >
            <span className="min-w-0 flex-1">{item.message}</span>
            {item.action && (
              <button
                onClick={() => {
                  item.action?.onClick();
                  dismiss(item.id);
                }}
                className="shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold text-foreground underline underline-offset-2 hover:opacity-80"
              >
                {item.action.label}
              </button>
            )}
            <button
              onClick={() => dismiss(item.id)}
              aria-label={t.feedback.close}
              className="shrink-0 text-muted hover:text-foreground"
            >
              ×
            </button>
          </div>
        ))}
      </div>

      {dialog && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) answer(false);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={dialog.title}
            className="w-full max-w-sm rounded-card border border-border bg-surface p-6 shadow-2xl transition-all duration-150 starting:scale-95 starting:opacity-0"
          >
            <h2 className="font-display text-lg font-medium">{dialog.title}</h2>
            {dialog.message && <p className="mt-2 text-sm text-muted">{dialog.message}</p>}
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => answer(false)}
                className="rounded-control px-4 py-2 text-sm text-muted hover:bg-surface-2 hover:text-foreground"
              >
                {t.feedback.cancel}
              </button>
              <button
                ref={confirmButtonRef}
                onClick={() => answer(true)}
                className={`rounded-control px-4 py-2 text-sm font-medium ${
                  dialog.danger
                    ? "bg-danger text-white hover:opacity-90"
                    : "bg-primary text-primary-foreground hover:opacity-90"
                }`}
              >
                {dialog.confirmLabel ?? t.feedback.confirm}
              </button>
            </div>
          </div>
        </div>
      )}
    </FeedbackContext.Provider>
  );
}
