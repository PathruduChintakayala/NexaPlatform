import type { PropsWithChildren } from "react";

interface UiCardProps extends PropsWithChildren {
  title: string;
  subtitle?: string;
}

export function UiCard({ title, subtitle, children }: UiCardProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      {subtitle ? <p className="mt-1 text-sm text-slate-500">{subtitle}</p> : null}
      <div className="mt-4">{children}</div>
    </div>
  );
}
