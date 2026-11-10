"use client";

import { useEffect, useState } from "react";

import {
  formatCounts,
  formatDuration,
  overallProgress,
  stageProgress,
  type StageName,
  type StageStep,
  type StreamStatus,
} from "@/lib/stream-state";
import { CheckIcon, ChevronDownIcon } from "./Icons";

interface StageRailProps {
  stages: StageStep[];
  status: StreamStatus;
  elapsedMs: number | null;
  storyCount: number | null;
  coverageStatus: string | null;
}

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

const DETAIL_STYLES: Record<StageStep["state"], string> = {
  pending: "text-ink-muted",
  active: "text-accent",
  done: "text-ink-muted",
  failed: "text-error",
  interrupted: "text-warning",
};

export function StageRail({
  stages,
  status,
  elapsedMs,
  storyCount,
  coverageStatus,
}: StageRailProps) {
  const [now, setNow] = useState(() => Date.now());
  const [overrides, setOverrides] = useState<
    Partial<Record<StageName, boolean>>
  >({});

  useEffect(() => {
    if (status !== "streaming") return;

    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [status]);

  const completed = stages.filter((step) => step.state === "done").length;
  const latestStage = stages.reduce<StageStep | null>((latest, step) => {
    if (!step.at) return latest;
    if (!latest?.at) return step;
    return Date.parse(step.at) > Date.parse(latest.at) ? step : latest;
  }, null);

  function isOpen(step: StageStep): boolean {
    const override = overrides[step.stage];
    if (override !== undefined) return override;
    if (step.state === "active" || step.state === "interrupted") return true;
    return (
      status === "streaming" &&
      step.state === "done" &&
      step.stage === latestStage?.stage
    );
  }

  function toggle(step: StageStep) {
    const next = !isOpen(step);
    setOverrides((previous) => ({ ...previous, [step.stage]: next }));
  }

  const completedParts =
    status === "done"
      ? [
          elapsedMs !== null ? `in ${formatDuration(elapsedMs)}` : null,
          storyCount !== null
            ? `· ${storyCount} ${storyCount === 1 ? "story" : "stories"}`
            : null,
          coverageStatus ? `· coverage ${coverageStatus}` : null,
        ].filter((part): part is string => Boolean(part))
      : [];

  const header =
    status === "done"
      ? ["Completed", ...completedParts].join(" ")
      : status === "streaming"
        ? `Building your brief · ${completed} of ${stages.length} stages done`
        : status === "stopped"
          ? "Run stopped"
          : "Run failed";

  const headerTone =
    status === "error"
      ? "text-error"
      : status === "stopped"
        ? "text-warning"
        : "text-ink-secondary";

  const progress = overallProgress(stages);
  const globalFill =
    status === "error"
      ? "bg-error"
      : status === "stopped"
        ? "bg-warning"
        : status === "done"
          ? "bg-success"
          : "bg-accent";

  return (
    <section aria-label="Brief progress" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <div className="flex items-center gap-2">
          {status === "done" ? (
            <CheckIcon className="text-success" />
          ) : (
            <span
              aria-hidden="true"
              className={`h-1.5 w-1.5 rounded-full ${
                status === "streaming"
                  ? "bg-accent stage-pulse"
                  : status === "error"
                    ? "bg-error"
                    : "bg-warning"
              }`}
            />
          )}
          <p className={`text-[13px] font-medium ${headerTone}`}>{header}</p>
        </div>

        <div className="flex items-center gap-3">
          <span className="font-mono text-[11px] text-ink-muted">
            {progress}%
          </span>
          <div
            className="h-1 w-24 overflow-hidden rounded-full bg-surface-raised"
            role="progressbar"
            aria-label="Run progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress}
          >
            <div
              className={`h-full rounded-full transition-[width] duration-500 ${globalFill}`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      <div className="space-y-2">
        {stages.map((step) => (
          <StageCard
            key={step.stage}
            step={step}
            open={isOpen(step)}
            now={now}
            onToggle={() => toggle(step)}
          />
        ))}
      </div>
    </section>
  );
}

function StageCard({
  step,
  open,
  now,
  onToggle,
}: {
  step: StageStep;
  open: boolean;
  now: number;
  onToggle: () => void;
}) {
  const progress = stageProgress(step);
  const borderClass =
    step.state === "active"
      ? "border-line-strong"
      : step.state === "failed"
        ? "border-error/30"
        : step.state === "interrupted"
          ? "border-warning/25"
          : "border-line";

  return (
    <details
      open={open}
      className={`group rounded-lg border bg-surface ${borderClass}`}
    >
      <summary
        aria-current={step.state === "active" ? "step" : undefined}
        onClick={(event) => {
          event.preventDefault();
          onToggle();
        }}
        className="flex cursor-pointer list-none items-start justify-between gap-4 px-4 py-3 [&::-webkit-details-marker]:hidden"
      >
        <span className="min-w-0">
          <span className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT_STYLES[step.state]}`}
            />
            <span
              className={`truncate text-[13px] font-medium ${LABEL_STYLES[step.state]}`}
            >
              {step.label}
            </span>
          </span>
          <span
            className={`mt-1 block pl-4 font-mono text-[11px] leading-4 ${DETAIL_STYLES[step.state]}`}
          >
            {headerDetail(step, now)}
            {step.state === "active" && progress
              ? ` · ${progress.percent}%`
              : ""}
          </span>
        </span>
        <ChevronDownIcon className="mt-0.5 shrink-0 text-ink-muted transition-transform duration-200 group-open:rotate-180" />
      </summary>

      <div className="border-t border-line px-4 pb-4 pt-3">
        <StageBody step={step} now={now} />
      </div>
    </details>
  );
}

function StageBody({ step, now }: { step: StageStep; now: number }) {
  if (step.state === "pending") {
    return (
      <p className="text-[12px] leading-5 text-ink-muted">
        This stage has not started yet.
      </p>
    );
  }

  const live = liveElapsed(step, now);
  const duration = step.state === "active" ? live : step.elapsedMs;
  const durationText =
    step.state === "active" && live !== null
      ? formatLive(live)
      : duration !== null
        ? formatDuration(duration)
        : "—";

  const timeLabel =
    step.state === "active"
      ? "Started"
      : step.state === "done"
        ? "Finished"
        : "Updated";

  return (
    <div className="space-y-3">
      <StageProgressBar step={step} />
      <dl className="grid gap-x-8 gap-y-1.5 text-[12px] leading-5 sm:grid-cols-2">
        <div className="flex items-baseline justify-between gap-4 sm:justify-start sm:gap-2">
          <dt className="text-ink-muted">{timeLabel}</dt>
          <dd className="font-mono text-ink-secondary">
            {formatClock(step.state === "active" ? step.startedAt : step.at)}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-4 sm:justify-start sm:gap-2">
          <dt className="text-ink-muted">Duration</dt>
          <dd className="font-mono text-ink-secondary">{durationText}</dd>
        </div>
        {Object.entries(step.counts)
          .filter(([key]) => key !== "done" && key !== "total")
          .map(([key, value]) => (
          <div
            key={key}
            className="flex items-baseline justify-between gap-4 sm:justify-start sm:gap-2"
          >
            <dt className="capitalize text-ink-muted">
              {key.replace(/_/g, " ")}
            </dt>
            <dd className="font-mono text-ink-secondary">{value}</dd>
          </div>
        ))}
      </dl>

      {step.message && step.state !== "failed" ? (
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-muted">
            Note
          </p>
          <p className="mt-1 break-words font-mono text-[11px] leading-5 text-ink-secondary">
            {step.message}
          </p>
        </div>
      ) : null}

      {step.state === "active" ? (
        <p className="flex items-center gap-2 text-[11px] leading-4 text-ink-muted">
          <span
            aria-hidden="true"
            className="stage-pulse h-1 w-1 rounded-full bg-accent"
          />
          Waiting for the next update...
        </p>
      ) : null}

      {step.state === "interrupted" ? (
        <p className="text-[12px] leading-5 text-warning">
          Stopped before this stage finished.
        </p>
      ) : null}

      {step.state === "failed" ? (
        <p className="text-[12px] leading-5 text-error">
          {step.message ?? "This stage failed."}
        </p>
      ) : null}
    </div>
  );
}

function StageProgressBar({ step }: { step: StageStep }) {
  const progress = stageProgress(step);
  const percent = progress?.percent ?? null;
  const label =
    step.state === "done"
      ? "Complete"
      : progress
        ? `${progress.done} of ${progress.total}`
        : step.state === "failed"
          ? "Failed"
          : step.state === "interrupted"
            ? "Interrupted"
            : "In progress";

  const fill =
    step.state === "failed"
      ? "bg-error"
      : step.state === "interrupted"
        ? "bg-warning"
        : step.state === "done"
          ? "bg-success"
          : "bg-accent";

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-muted">
          Progress
        </span>
        <span className="font-mono text-[11px] text-ink-secondary">
          {label}
          {percent !== null ? ` · ${percent}%` : ""}
        </span>
      </div>
      <div
        className="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-raised"
        role="progressbar"
        aria-label={`${step.label} progress`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent ?? undefined}
      >
        {percent !== null ? (
          <div
            className={`h-full rounded-full transition-[width] duration-500 ${fill}`}
            style={{ width: `${percent}%` }}
          />
        ) : (
          <div className={`h-full w-1/3 animate-pulse rounded-full ${fill}`} />
        )}
      </div>
    </div>
  );
}

function headerDetail(step: StageStep, now: number): string {
  const counts = formatCounts(step.stage, step.counts);

  if (step.state === "pending") return "waiting";

  if (step.state === "active") {
    const live = liveElapsed(step, now);
    return [counts, live !== null ? `running ${formatLive(live)}` : "running"]
      .filter(Boolean)
      .join(" · ");
  }

  if (step.state === "interrupted" || step.state === "failed") {
    return [counts, step.state].filter(Boolean).join(" · ");
  }

  return (
    [counts, formatDuration(step.elapsedMs)].filter(Boolean).join(" · ") ||
    "done"
  );
}

function liveElapsed(step: StageStep, now: number): number | null {
  if (!step.startedAt) return null;
  const started = Date.parse(step.startedAt);
  if (Number.isNaN(started)) return null;
  return Math.max(0, now - started);
}

function formatLive(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatClock(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
