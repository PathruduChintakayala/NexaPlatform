import { UiCard } from "@nexa/ui";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { AuthDevToken } from "../components/auth-dev-token";
import { HealthPanel } from "../components/health-panel";
import { SampleScopeForm } from "../components/sample-form";

const modules = [
  { key: "admin", label: "Admin" },
  { key: "sales", label: "Sales" },
  { key: "ops", label: "Ops" },
  { key: "reports", label: "Reports" },
  { key: "crm", label: "CRM" },
  { key: "catalog", label: "Catalog" },
  { key: "revenue", label: "Revenue" },
  { key: "billing", label: "Billing" },
  { key: "payments", label: "Payments" },
  { key: "support", label: "Support" }
] as const;

export default function LauncherPage() {
  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold">Nexa App Launcher</h1>
        <p className="text-sm text-slate-500">Single-tenant foundation with multi-legal-entity, multi-region, and multi-currency context.</p>
      </section>
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {modules.map((module) => (
          <UiCard key={module.key} title={module.label} subtitle="Module placeholder">
            <Link href={`/${module.key}`} className="inline-flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-slate-900">
              Open module <ArrowRight className="h-4 w-4" />
            </Link>
          </UiCard>
        ))}
      </section>
      <section className="grid gap-4 lg:grid-cols-3">
        <AuthDevToken />
        <HealthPanel />
        <SampleScopeForm />
      </section>
    </div>
  );
}
