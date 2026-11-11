"use client";

import type { ChatRun } from "@/app/types";
import { stagesFromEvents } from "@/lib/chat-state";
import { formatDuration } from "@/lib/stream-state";
import { ChevronDownIcon } from "./Icons";
import { StageList } from "./StageList";

const DOTS: Record<ChatRun["status"], string> = {
  completed: "bg-success",
  failed: "bg-error",
  stopped: "bg-warning",
};

export function RunSummary({ run }: { run: ChatRun }) {
  const stages = stagesFromEvents(run.stages);
  const detail = [
    formatDuration(run.elapsed_ms),
    run.story_count !== null
      ? `${run.story_count} ${run.story_count === 1 ? "story" : "stories"}`
      : null,
    run.coverage_status ? `coverage ${run.coverage_status}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <details className="group mt-4 rounded-lg border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <span className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
          <span
            aria-hidden="true"
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOTS[run.status]}`}
          />
          <span className="text-[13px] font-medium text-ink-secondary">
            Execution
          </span>
          <span className="font-mono text-[11px] text-ink-muted">
            {run.status}
            {detail ? ` · ${detail}` : ""}
          </span>
        </span>
        <ChevronDownIcon className="shrink-0 text-ink-muted transition-transform duration-200 group-open:rotate-180" />
      </summary>
      <div className="border-t border-line">
        {stages.length > 0 ? (
          <StageList stages={stages} />
        ) : (
          <p className="px-4 py-3 text-[12px] leading-5 text-ink-muted">
            No stages were recorded for this run.
          </p>
        )}
      </div>
    </details>
  );
}
