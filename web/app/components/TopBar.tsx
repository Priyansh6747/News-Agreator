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

interface TopBarProps {
  apiStatus: ApiStatus;
  compact?: boolean;
  onNewChat?: () => void;
}

export function TopBar({
  apiStatus,
  compact = false,
  onNewChat,
}: TopBarProps) {
  return (
    <header
      className={`flex items-center justify-between gap-4 ${
        compact ? "py-3" : "py-5"
      }`}
    >
      <div className="flex items-center gap-2.5">
        <span aria-hidden="true" className="brand-dot" />
        <span className="text-[14px] font-semibold tracking-[-0.01em] text-ink">
          NewsAgreator
        </span>
      </div>

      <div className="flex items-center gap-2">
        {onNewChat ? (
          <button
            type="button"
            onClick={onNewChat}
            aria-label="Start a new chat"
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-line bg-surface-raised text-ink-muted transition-colors duration-150 hover:bg-surface-hover hover:text-ink active:scale-[0.97]"
          >
            <PlusIcon />
          </button>
        ) : null}
        <span
          className={`inline-flex items-center gap-2 rounded-full border border-line bg-surface-raised px-3 py-1.5 text-[11px] font-medium tracking-[0.02em] ${TONES[apiStatus]}`}
        >
          <span
            aria-hidden="true"
            className={`h-1.5 w-1.5 rounded-full ${DOTS[apiStatus]}`}
          />
          {LABELS[apiStatus]}
        </span>
      </div>
    </header>
  );
}

function PlusIcon() {
  return (
    <svg
      aria-hidden="true"
      width="16"
      height="16"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
    >
      <path d="M10 4.5v11" />
      <path d="M4.5 10h11" />
    </svg>
  );
}
