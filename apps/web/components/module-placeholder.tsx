interface ModulePlaceholderProps {
  title: string;
  description: string;
}

export function ModulePlaceholder({ title, description }: ModulePlaceholderProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-slate-500">{description}</p>
      <p className="mt-4 rounded-md bg-slate-100 p-3 text-xs text-slate-600">
        TODO: implement domain endpoints, application services, and UI flows for this module.
      </p>
    </div>
  );
}
