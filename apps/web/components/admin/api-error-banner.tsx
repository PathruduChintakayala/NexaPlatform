import React from "react";

interface ApiErrorBannerProps {
  message: string | null;
}

export function ApiErrorBanner({ message }: ApiErrorBannerProps) {
  if (!message) {
    return null;
  }

  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {message}
    </div>
  );
}
