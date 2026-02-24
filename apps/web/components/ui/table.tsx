import React from "react";

import type { PropsWithChildren } from "react";

export function Table({ children }: PropsWithChildren) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 bg-white text-sm">{children}</table>
    </div>
  );
}

export function Th({ children }: PropsWithChildren) {
  return <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">{children}</th>;
}

export function Td({ children }: PropsWithChildren) {
  return <td className="px-3 py-3 align-top text-slate-700">{children}</td>;
}
