"use client";

import { useSyncExternalStore, useState } from "react";

import { useApiStatus } from "@/lib/useApiStatus";
import { useBriefStream } from "@/lib/useBriefStream";
import { BriefView } from "./components/BriefView";
import { Composer } from "./components/Composer";
import { CoveragePill } from "./components/CoveragePill";
import { Orb } from "./components/Orb";
import { StageRail } from "./components/StageRail";
import { SuggestionCards } from "./components/SuggestionCards";
import { TopBar } from "./components/TopBar";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8012";
const STREAM_ENDPOINT = `${API_BASE}/api/v1/brief/stream`;
const HEALTH_ENDPOINT = `${API_BASE}/health`;

export default function Home() {
  const [input, setInput] = useState("");
  const mounted = useMounted();
  const apiStatus = useApiStatus(HEALTH_ENDPOINT);
  const { state, stages, status, brief, error, elapsedMs, start, stop } =
    useBriefStream({ endpoint: STREAM_ENDPOINT });

  const streaming = status === "streaming";
  const active = state.query !== null;
  const greeting = mounted ? timeGreeting() : "Good evening.";
  const hasStages = Object.keys(state.stages).length > 0;

  function submit(explicit?: string) {
    const query = (explicit ?? input).trim();
    if (query.length < 2 || streaming) return;
    setInput("");
    void start(query);
  }

  const liveMessage =
    status === "streaming"
      ? state.query
        ? `Working on ${state.query}.`
        : "Starting the brief."
      : status === "done"
        ? "Brief ready."
        : status === "stopped"
          ? "Brief stopped."
          : "";

  const statusLine =
    status === "streaming"
      ? "Working through the sources..."
      : status === "done"
        ? "Brief ready."
        : status === "stopped"
          ? "Stopped. The stages completed so far are kept."
          : status === "error"
            ? "The run did not finish."
            : "";

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[960px] flex-col px-4 pb-12 sm:px-8 lg:px-10">
      <TopBar apiStatus={apiStatus} />

      <p role="status" aria-live="polite" className="sr-only">
        {liveMessage}
      </p>

      {!active ? (
        <div className="flex flex-1 flex-col items-center pt-[clamp(56px,11vh,120px)]">
          <div className="enter">
            <Orb size="lg" />
          </div>

          <h1
            className="enter mt-6 text-center text-[26px] leading-[1.22] tracking-[-0.02em] text-ink-strong sm:text-[34px] sm:leading-[1.18] sm:tracking-[-0.025em]"
            style={{ animationDelay: "60ms" }}
          >
            {greeting}
            <br />
            What should I brief you on?
          </h1>

          <div
            className="enter mt-10 w-full"
            style={{ animationDelay: "120ms" }}
          >
            <Composer
              value={input}
              onChange={setInput}
              onSubmit={() => submit()}
              onStop={stop}
              streaming={streaming}
            />
          </div>

          <div
            className="enter mt-7 w-full"
            style={{ animationDelay: "180ms" }}
          >
            <SuggestionCards onPick={submit} />
          </div>
        </div>
      ) : (
        <div className="flex flex-1 flex-col gap-6 pb-8" aria-busy={streaming}>
          <div className="flex items-center gap-3 pt-3">
            <Orb size="sm" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="min-w-0 truncate text-[22px] font-semibold tracking-[-0.02em] text-ink-strong sm:text-[24px]">
                  {state.query}
                </h1>
                {brief ? <CoveragePill status={brief.coverage.status} /> : null}
              </div>
              <p className="mt-1 text-[12px] leading-5 text-ink-muted">
                {statusLine}
              </p>
            </div>
          </div>

          <Composer
            value={input}
            onChange={setInput}
            onSubmit={() => submit()}
            onStop={stop}
            streaming={streaming}
            hasError={status === "error"}
          />

          {streaming || hasStages ? (
            <StageRail
              key={state.startedAt ?? "idle"}
              stages={stages}
              status={status}
              elapsedMs={elapsedMs}
              storyCount={brief?.stories.length ?? null}
              coverageStatus={brief?.coverage.status ?? null}
            />
          ) : null}

          {error ? (
            <div
              role="alert"
              className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-error/30 bg-error-soft px-4 py-3"
            >
              <p className="min-w-0 text-[13px] leading-5 text-error">
                {error}
              </p>
              {state.query ? (
                <button
                  type="button"
                  onClick={() => submit(state.query ?? undefined)}
                  className="shrink-0 rounded-full border border-error/30 px-3 py-1.5 text-[12px] font-medium text-error transition-colors hover:bg-[var(--error-soft)]"
                >
                  Retry
                </button>
              ) : null}
            </div>
          ) : null}

          {brief ? <BriefView brief={brief} /> : null}
        </div>
      )}

      <p className="mt-auto pt-10 text-center text-[11px] leading-4 text-ink-muted">
        Free-source news briefs. Coverage is reported, not hidden.
      </p>
    </main>
  );
}

function timeGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning.";
  if (hour < 18) return "Good afternoon.";
  return "Good evening.";
}

const subscribeToMount = () => () => {};

function useMounted(): boolean {
  return useSyncExternalStore(
    subscribeToMount,
    () => true,
    () => false,
  );
}
