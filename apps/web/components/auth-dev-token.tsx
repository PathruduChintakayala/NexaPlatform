"use client";

import { useEffect, useState } from "react";

import { getDevToken, setDevToken } from "../lib/auth-storage";

export function AuthDevToken() {
  const [token, setToken] = useState("");

  useEffect(() => {
    setToken(getDevToken());
  }, []);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-base font-semibold">Dev Auth Token</h3>
      <p className="mt-1 text-sm text-slate-500">Stored in local storage for local development only.</p>
      <input
        className="mt-3 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        value={token}
        onChange={(event) => {
          const value = event.target.value;
          setToken(value);
          setDevToken(value);
        }}
        placeholder="Bearer token"
      />
    </div>
  );
}
