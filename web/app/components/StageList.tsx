"use client";

import {
  formatCounts,
  formatDuration,
  type StageStep,
} from "@/lib/stream-state";

const DOT_STYLES: Record<StageStep["state"], string> = {
  pending: "bg-ink-faint opacity-40",
  active: "bg-accent stage-pulse",
  done: "bg-success",
  failed: "bg-error",
  interrupted: "bg-warning",
};

const LABEL_STYLES: Record<StageStep["state"], string> = {
  pending: "text-ink-muted",
  active: "text-ink",
  done: "text-ink-secondary",
  failed: "text-error",
  interrupted: "text-warning",
};

export function StageList({ stages }: { stages: StageStep[] }) {
  return (
    <ol className="divide-y divide-line">
      {stages.map((step) => {
        const detail =
          step.state === "active"
            ? "running"
            : [
                formatCounts(step.stage, step.counts),
                formatDuration(step.elapsedMs),
              ]
                .filter(Boolean)
                .join(" · ") || "waiting";

        return (
          <li
            key={step.stage}
            className="flex items-center justify-between gap-4 px-4 py-2.5"
          >
            <span className="flex min-w-0 items-center gap-2.5">
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT_STYLES[step.state]}`}
              />
              <span
                className={`truncate text-[12px] font-medium ${LABEL_STYLES[step.state]}`}
              >
                {step.label}
              </span>
            </span>
            <span className="shrink-0 font-mono text-[11px] text-ink-muted">
              {detail}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
