"use client";

import React from "react";
import { RouteGuard } from "../../components/route-guard";
import { Button } from "../../components/ui/button";

export default function AdminPage() {
  return (
    <RouteGuard requiredRoles={["admin", "system.admin"]}>
      <section className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <header>
          <h1 className="text-2xl font-semibold">Admin Console</h1>
          <p className="text-sm text-slate-600">Choose a management area below.</p>
        </header>

        <div className="grid gap-4 md:grid-cols-3">
          <a href="/admin/roles" className="rounded-lg border border-slate-200 p-4">
            <h2 className="text-base font-semibold">Roles</h2>
            <p className="mt-1 text-sm text-slate-600">Create, update, delete, and map permissions to roles.</p>
            <Button className="mt-4">Open roles</Button>
          </a>
          <a href="/admin/permissions" className="rounded-lg border border-slate-200 p-4">
            <h2 className="text-base font-semibold">Permissions</h2>
            <p className="mt-1 text-sm text-slate-600">Manage resources, actions, and scope definitions.</p>
            <Button className="mt-4">Open permissions</Button>
          </a>
          <a href="/admin/user-roles" className="rounded-lg border border-slate-200 p-4">
            <h2 className="text-base font-semibold">User Roles</h2>
            <p className="mt-1 text-sm text-slate-600">Assign and revoke roles, search by user, view all assignments.</p>
            <Button className="mt-4">Open user roles</Button>
          </a>
        </div>
      </section>
    </RouteGuard>
  );
}
