export function CoveragePill({ status }: { status: string }) {
  const tone =
    status === "complete"
      ? "bg-success-soft text-success"
      : status === "partial"
        ? "bg-warning-soft text-warning"
        : "bg-error-soft text-error";

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.08em] ${tone}`}
    >
      coverage {status}
    </span>
  );
}
