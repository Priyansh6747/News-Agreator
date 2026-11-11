"use client";

import type { ChatToolState } from "@/lib/chat-state";
import type { StageStep, StreamStatus } from "@/lib/stream-state";
import { Orb } from "./Orb";
import { StageRail } from "./StageRail";

interface ExecutionPaneProps {
  query: string;
  stages: StageStep[];
  status: StreamStatus;
  elapsedMs: number | null;
  storyCount: number | null;
  coverageStatus: string | null;
  tool: ChatToolState | null;
}

export function ExecutionPane({
  query,
  stages,
  status,
  elapsedMs,
  storyCount,
  coverageStatus,
  tool,
}: ExecutionPaneProps) {
  const started = stages.some((step) => step.state !== "pending");

  return (
    <div className="space-y-5 px-5 py-5">
      <div>
        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
          Run
        </p>
        <div className="mt-3 flex items-center gap-3">
          <Orb size="sm" />
          <div className="min-w-0">
            <p className="truncate text-[14px] font-medium text-ink">
              {query}
            </p>
            <p className="mt-0.5 font-mono text-[11px] text-ink-muted">
              {tool
                ? `news_brief · ${tool.status}`
                : "understanding the question"}
            </p>
          </div>
        </div>
      </div>

      {started ? (
        <StageRail
          stages={stages}
          status={status}
          elapsedMs={elapsedMs}
          storyCount={storyCount}
          coverageStatus={coverageStatus}
        />
      ) : (
        <div className="rounded-lg border border-line bg-surface px-4 py-6 text-center">
          <p className="text-[13px] leading-5 text-ink-secondary">
            Thinking about the best query...
          </p>
          <p className="mt-1 text-[12px] leading-5 text-ink-muted">
            The news run starts as soon as the tool is called.
          </p>
        </div>
      )}
    </div>
  );
}
