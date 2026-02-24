import type { SelectHTMLAttributes } from "react";
import React from "react";

export function Select({ className = "", children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-500 focus:outline-none ${className}`}
      {...props}
    >
      {children}
    </select>
  );
}
