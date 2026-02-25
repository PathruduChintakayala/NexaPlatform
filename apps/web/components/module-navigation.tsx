"use client";

import {
  BadgeDollarSign,
  BarChart3,
  Building2,
  ClipboardList,
  CreditCard,
  Headset,
  LayoutGrid,
  Shield,
  Store,
  Wrench,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType } from "react";

const moduleItems: { key: string; label: string; href: string; icon: ComponentType<{ className?: string }> }[] = [
  { key: "admin", label: "Admin", href: "/admin", icon: Building2 },
  { key: "sales-hub", label: "Sales", href: "/sales", icon: Users },
  { key: "ops-hub", label: "Ops", href: "/ops", icon: Wrench },
  { key: "reports-hub", label: "Reports", href: "/reports", icon: BarChart3 },
  { key: "crm", label: "CRM", href: "/crm", icon: Users },
  { key: "catalog", label: "Catalog", href: "/catalog", icon: Store },
  { key: "revenue", label: "Revenue", href: "/revenue", icon: BadgeDollarSign },
  { key: "billing", label: "Billing", href: "/billing", icon: ClipboardList },
  { key: "payments", label: "Payments", href: "/payments", icon: CreditCard },
  { key: "support", label: "Support", href: "/support", icon: Headset }
];

export function ModuleNavigation() {
  const pathname = usePathname();

  return (
    <nav className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <LayoutGrid className="h-5 w-5" />
        <p className="text-sm font-semibold">App Launcher</p>
      </div>
      <ul className="space-y-1">
        <li>
          <Link
            href="/"
            className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm ${pathname === "/" ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`}
          >
            <Shield className="h-4 w-4" />
            Overview
          </Link>
        </li>
        {moduleItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <li key={item.key}>
              <Link
                href={item.href}
                className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm ${active ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            </li>
          );
        })}
        <li>
          <Link
            href="/finance"
            className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm ${pathname === "/finance" || pathname.startsWith("/finance/") ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`}
          >
            <BarChart3 className="h-4 w-4" />
            Finance
          </Link>
        </li>
      </ul>
    </nav>
  );
}
