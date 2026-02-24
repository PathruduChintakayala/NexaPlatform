"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const scopeSchema = z.object({
  legalEntity: z.string().min(2),
  region: z.enum(["global", "us", "eu", "apac"]),
  currency: z.enum(["USD", "EUR", "GBP"])
});

type ScopeForm = z.infer<typeof scopeSchema>;

export function SampleScopeForm() {
  const [submitted, setSubmitted] = useState<ScopeForm | null>(null);
  const form = useForm<ScopeForm>({
    resolver: zodResolver(scopeSchema),
    defaultValues: {
      legalEntity: "default",
      region: "global",
      currency: "USD"
    }
  });

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-base font-semibold">Scope Form (RHF + Zod)</h3>
      <form
        className="mt-4 grid gap-3"
        onSubmit={form.handleSubmit((values) => {
          setSubmitted(values);
        })}
      >
        <input
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          placeholder="Legal Entity"
          {...form.register("legalEntity")}
        />
        <select className="rounded-md border border-slate-300 px-3 py-2 text-sm" {...form.register("region")}>
          <option value="global">global</option>
          <option value="us">us</option>
          <option value="eu">eu</option>
          <option value="apac">apac</option>
        </select>
        <select className="rounded-md border border-slate-300 px-3 py-2 text-sm" {...form.register("currency")}>
          <option value="USD">USD</option>
          <option value="EUR">EUR</option>
          <option value="GBP">GBP</option>
        </select>
        <button className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white" type="submit">
          Save
        </button>
      </form>
      {submitted ? (
        <pre className="mt-3 rounded-md bg-slate-100 p-3 text-xs">{JSON.stringify(submitted, null, 2)}</pre>
      ) : null}
    </div>
  );
}
