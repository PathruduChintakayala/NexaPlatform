import React from "react";
import Link from "next/link";

interface AccessDeniedPanelProps {
  statusCode: 401 | 403;
}

export function AccessDeniedPanel({ statusCode }: AccessDeniedPanelProps) {
  const title = statusCode === 401 ? "Unauthorized" : "Forbidden";
  const detail =
    statusCode === 401
      ? "You need to sign in with a valid token to access this page."
      : "Your current role does not have access to this page.";

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-2xl font-semibold">Access Denied ({statusCode})</h1>
      <p className="mt-2 text-sm text-slate-600">
        {title}: {detail}
      </p>
      <div className="mt-4">
        <Link className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-100" href="/">
          Return to home
        </Link>
      </div>
    </section>
  );
}
