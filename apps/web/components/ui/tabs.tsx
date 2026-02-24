"use client";

import type { ReactNode } from "react";
import { useState } from "react";

interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
}

interface TabsProps {
  items: TabItem[];
  defaultTab?: string;
}

export function Tabs({ items, defaultTab }: TabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab ?? items[0]?.id);
  const active = items.find((item) => item.id === activeTab) ?? items[0];

  if (!active) {
    return null;
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2">
        {items.map((item) => {
          const isActive = item.id === active.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setActiveTab(item.id)}
              className={`rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}`}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      <div className="pt-4">{active.content}</div>
    </div>
  );
}
