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
          <div className="mx-auto flex min-h-screen w-full max-w-7xl gap-6 px-4 py-6">
            <aside className="w-72 shrink-0">
              <ModuleNavigation />
            </aside>
            <main className="flex-1">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
