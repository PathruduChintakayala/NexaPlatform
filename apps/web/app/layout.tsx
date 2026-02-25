import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import { ModuleNavigation } from "../components/module-navigation";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Nexa Platform",
  description: "Modular monolith SaaS suite"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <div className="mx-auto min-h-screen w-full max-w-7xl px-4 py-6">
            <header className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h1 className="text-lg font-semibold">Nexa Platform</h1>
              <p className="text-sm text-slate-600">Admin, Sales, Ops, and Reports roll-up v1</p>
            </header>
            <div className="flex gap-6">
              <aside className="w-72 shrink-0">
                <ModuleNavigation />
              </aside>
              <main className="flex-1">{children}</main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
