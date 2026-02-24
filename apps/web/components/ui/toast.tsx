import type { ApiToastMessage } from "../../lib/api";

interface ToastProps {
  message: string | ApiToastMessage | null;
  tone?: "success" | "error" | "info";
}

export type ToastMessageValue = ToastProps["message"];

const toneClass = {
  success: "border-emerald-200 bg-emerald-50 text-emerald-800",
  error: "border-red-200 bg-red-50 text-red-800",
  info: "border-slate-200 bg-slate-100 text-slate-700"
};

export function Toast({ message, tone = "info" }: ToastProps) {
  if (!message) {
    return null;
  }

  const text = typeof message === "string" ? message : message.message;
  const correlationId = typeof message === "string" ? null : message.correlationId;

  return (
    <div className={`rounded-md border px-3 py-2 text-sm ${toneClass[tone]}`}>
      <p>{text}</p>
      {correlationId ? (
        <div className="mt-1 flex items-center gap-2 text-xs">
          <span>Correlation ID: {correlationId}</span>
          <button
            type="button"
            className="rounded border border-current px-1.5 py-0.5 text-[11px]"
            onClick={() => void navigator.clipboard.writeText(correlationId)}
          >
            Copy
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function toastText(message: string | ApiToastMessage | null): string {
  if (!message) {
    return "";
  }
  return typeof message === "string" ? message : message.message;
}
