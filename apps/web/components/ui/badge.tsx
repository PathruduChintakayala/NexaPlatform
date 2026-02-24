import type { PropsWithChildren } from "react";

interface BadgeProps extends PropsWithChildren {
  tone?: "default" | "success" | "warning" | "danger";
}

const toneClass = {
  default: "bg-slate-100 text-slate-700",
  success: "bg-emerald-100 text-emerald-700",
  warning: "bg-amber-100 text-amber-700",
  danger: "bg-red-100 text-red-700"
};

export function Badge({ children, tone = "default" }: BadgeProps) {
  return <span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${toneClass[tone]}`}>{children}</span>;
}
