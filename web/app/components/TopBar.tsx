import type { ApiStatus } from "@/lib/useApiStatus";

const LABELS: Record<ApiStatus, string> = {
  checking: "api checking",
  online: "api online",
  offline: "api offline",
};

const TONES: Record<ApiStatus, string> = {
  checking: "text-ink-muted",
  online: "text-success",
  offline: "text-error",
};

const DOTS: Record<ApiStatus, string> = {
  checking: "bg-ink-muted",
  online: "bg-success",
  offline: "bg-error",
};

export function TopBar({ apiStatus }: { apiStatus: ApiStatus }) {
  return (
    <header className="flex items-center justify-between gap-4 py-5">
      <div className="flex items-center gap-2.5">
        <span aria-hidden="true" className="brand-dot" />
        <span className="text-[14px] font-semibold tracking-[-0.01em] text-ink">
          NewsAgreator
        </span>
      </div>

      <span
        className={`inline-flex items-center gap-2 rounded-full border border-line bg-surface-raised px-3 py-1.5 text-[11px] font-medium tracking-[0.02em] ${TONES[apiStatus]}`}
      >
        <span
          aria-hidden="true"
          className={`h-1.5 w-1.5 rounded-full ${DOTS[apiStatus]}`}
        />
        {LABELS[apiStatus]}
      </span>
    </header>
  );
}
