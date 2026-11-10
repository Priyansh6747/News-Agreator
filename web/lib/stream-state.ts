import type { Brief } from "@/app/types";

export const STAGE_ORDER = [
  "plan",
  "retrieve",
  "rank",
  "cluster",
  "score",
  "enrich",
  "brief",
  "present",
] as const;

export type StageName = (typeof STAGE_ORDER)[number];

export const STAGE_LABELS: Record<StageName, string> = {
  plan: "Planning",
  retrieve: "Retrieving",
  rank: "Ranking",
  cluster: "Clustering",
  score: "Scoring",
  enrich: "Reading",
  brief: "Writing brief",
  present: "Presenting",
};

const STAGE_STATES = ["started", "progress", "finished", "failed"] as const;
type StageState = (typeof STAGE_STATES)[number];

export type StreamStatus = "idle" | "streaming" | "done" | "error" | "stopped";

export interface StageEventPayload {
  stage: StageName;
  state: StageState;
  counts: Record<string, number>;
  message: string | null;
  elapsed_ms: number | null;
  at: string;
}

export interface StageRecord extends StageEventPayload {
  startedAt: string;
}

export interface BriefStreamState {
  status: StreamStatus;
  query: string | null;
  stages: Partial<Record<StageName, StageRecord>>;
  brief: Brief | null;
  error: string | null;
  startedAt: number | null;
  endedAt: number | null;
}

export interface StageStep {
  stage: StageName;
  label: string;
  state: "pending" | "active" | "done" | "failed" | "interrupted";
  counts: Record<string, number>;
  message: string | null;
  elapsedMs: number | null;
  at: string | null;
  startedAt: string | null;
}

export function createInitialState(): BriefStreamState {
  return {
    status: "idle",
    query: null,
    stages: {},
    brief: null,
    error: null,
    startedAt: null,
    endedAt: null,
  };
}

export function startRun(query: string, now = Date.now()): BriefStreamState {
  return {
    status: "streaming",
    query,
    stages: {},
    brief: null,
    error: null,
    startedAt: now,
    endedAt: null,
  };
}

export function applyStage(
  state: BriefStreamState,
  event: StageEventPayload,
): BriefStreamState {
  if (state.status !== "streaming") return state;

  const previous = state.stages[event.stage];
  return {
    ...state,
    stages: {
      ...state.stages,
      [event.stage]: {
        ...event,
        startedAt: previous?.startedAt ?? event.at,
      },
    },
  };
}

export function applyBrief(
  state: BriefStreamState,
  brief: Brief,
  now = Date.now(),
): BriefStreamState {
  return {
    ...state,
    status: "done",
    brief,
    error: null,
    endedAt: now,
  };
}

export function applyError(
  state: BriefStreamState,
  message: string,
  now = Date.now(),
): BriefStreamState {
  return {
    ...state,
    status: "error",
    error: message,
    endedAt: state.endedAt ?? now,
  };
}

export function markStopped(
  state: BriefStreamState,
  now = Date.now(),
): BriefStreamState {
  return {
    ...state,
    status: "stopped",
    error: null,
    endedAt: state.endedAt ?? now,
  };
}

export function finalizeWithoutBrief(state: BriefStreamState): BriefStreamState {
  if (state.status !== "streaming") return state;
  return applyError(
    state,
    "The stream ended before a brief was ready. Try again.",
  );
}

export function deriveStages(state: BriefStreamState): StageStep[] {
  const streaming = state.status === "streaming";

  return STAGE_ORDER.map((stage) => {
    const record = state.stages[stage];
    const label = STAGE_LABELS[stage];

    if (!record) {
      return {
        stage,
        label,
        state: "pending",
        counts: {},
        message: null,
        elapsedMs: null,
        at: null,
        startedAt: null,
      };
    }

    let stepState: StageStep["state"];
    if (record.state === "failed") {
      stepState = "failed";
    } else if (record.state === "finished") {
      stepState = "done";
    } else if (streaming) {
      stepState = "active";
    } else {
      stepState = "interrupted";
    }

    return {
      stage,
      label,
      state: stepState,
      counts: record.counts,
      message: record.message,
      elapsedMs: record.elapsed_ms,
      at: record.at,
      startedAt: record.startedAt,
    };
  });
}

export interface StageProgress {
  done: number;
  total: number;
  percent: number;
}

export function stageProgress(step: StageStep): StageProgress | null {
  if (step.state === "done") {
    return { done: 1, total: 1, percent: 100 };
  }
  if (step.state === "pending") {
    return null;
  }

  const done = step.counts.done;
  const total = step.counts.total;
  if (typeof done !== "number" || typeof total !== "number" || total <= 0) {
    return null;
  }

  const clamped = Math.min(Math.max(done, 0), total);
  return {
    done: clamped,
    total,
    percent: Math.round((clamped / total) * 100),
  };
}

export function overallProgress(stages: StageStep[]): number {
  if (stages.length === 0) return 0;

  let units = 0;
  for (const step of stages) {
    if (step.state === "done") {
      units += 1;
      continue;
    }
    if (
      step.state === "active" ||
      step.state === "failed" ||
      step.state === "interrupted"
    ) {
      const progress = stageProgress(step);
      if (progress) {
        units += progress.percent / 100;
      }
    }
  }

  return Math.round((units / stages.length) * 100);
}

export function formatCounts(
  stage: StageName,
  counts: Record<string, number>,
): string {
  const value = (key: string): number | null =>
    typeof counts[key] === "number" ? counts[key] : null;

  if (stage === "plan") {
    const phrasings = value("phrasings");
    return phrasings === null ? "" : count(phrasings, "phrasing");
  }
  if (stage === "retrieve") {
    const candidates = value("candidates");
    return candidates === null ? "" : count(candidates, "candidate");
  }
  if (stage === "rank") {
    const selected = value("selected");
    return selected === null ? "" : `${selected} selected`;
  }
  if (stage === "cluster" || stage === "score") {
    const clusters = value("clusters");
    return clusters === null ? "" : count(clusters, "cluster");
  }
  if (stage === "enrich") {
    const facts = value("facts");
    return facts === null ? "" : count(facts, "fact");
  }

  if (stage === "present") {
    const charts = value("charts");
    const locations = value("locations");
    return [
      charts === null ? null : count(charts, "chart"),
      locations === null ? null : count(locations, "location"),
    ]
      .filter((part): part is string => Boolean(part))
      .join(" · ");
  }

  const stories = value("stories");
  const facts = value("facts");
  const timeline = value("timeline");
  return [
    stories === null ? null : count(stories, "story", "stories"),
    facts === null ? null : count(facts, "fact"),
    timeline === null || timeline === 0 ? null : count(timeline, "timeline entry", "timeline entries"),
  ]
    .filter((part): part is string => Boolean(part))
    .join(" · ");
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseStageEvent(value: unknown): StageEventPayload | null {
  if (!isRecord(value)) return null;

  const stage = value.stage;
  const state = value.state;
  if (typeof stage !== "string" || !isStageName(stage)) return null;
  if (typeof state !== "string" || !isStageState(state)) return null;

  return {
    stage,
    state,
    counts: numberRecord(value.counts),
    message: typeof value.message === "string" ? value.message : null,
    elapsed_ms:
      typeof value.elapsed_ms === "number" && Number.isFinite(value.elapsed_ms)
        ? value.elapsed_ms
        : null,
    at: typeof value.at === "string" ? value.at : new Date().toISOString(),
  };
}

export function parseBrief(value: unknown): Brief | null {
  if (!isRecord(value)) return null;
  if (typeof value.query !== "string" || typeof value.answer !== "string") {
    return null;
  }
  if (typeof value.generated_at !== "string") return null;
  if (
    !Array.isArray(value.key_facts) ||
    !Array.isArray(value.timeline) ||
    !Array.isArray(value.disagreements) ||
    !Array.isArray(value.thin_sourcing) ||
    !Array.isArray(value.stories)
  ) {
    return null;
  }
  if (!isRecord(value.coverage)) return null;
  const coverage = value.coverage;
  if (
    typeof coverage.status !== "string" ||
    !Array.isArray(coverage.backends) ||
    !Array.isArray(coverage.attempts) ||
    !Array.isArray(coverage.notes) ||
    !isRecord(coverage.drops) ||
    !isRecord(coverage.text_status) ||
    !isRecord(coverage.timings_ms)
  ) {
    return null;
  }
  return value as unknown as Brief;
}

export function parseErrorMessage(value: unknown): string | null {
  if (!isRecord(value)) return null;
  if (typeof value.message === "string" && value.message.trim()) {
    return value.message;
  }
  return null;
}

function isStageName(value: string): value is StageName {
  return (STAGE_ORDER as readonly string[]).includes(value);
}

function isStageState(value: string): value is StageState {
  return (STAGE_STATES as readonly string[]).includes(value);
}

function numberRecord(value: unknown): Record<string, number> {
  if (!isRecord(value)) return {};
  const result: Record<string, number> = {};
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry === "number" && Number.isFinite(entry)) {
      result[key] = entry;
    }
  }
  return result;
}

function count(value: number, singular: string, plural = `${singular}s`): string {
  return `${value} ${value === 1 ? singular : plural}`;
}
