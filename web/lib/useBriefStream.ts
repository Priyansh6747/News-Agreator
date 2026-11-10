"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { Brief } from "@/app/types";
import { readSSE } from "./sse";
import {
  applyBrief,
  applyError,
  applyStage,
  createInitialState,
  deriveStages,
  finalizeWithoutBrief,
  isRecord,
  markStopped,
  parseBrief,
  parseErrorMessage,
  parseStageEvent,
  startRun,
  type BriefStreamState,
  type StageStep,
  type StreamStatus,
} from "./stream-state";

const WATCHDOG_MS = 150_000;

export interface UseBriefStreamOptions {
  endpoint: string;
}

export interface UseBriefStreamResult {
  state: BriefStreamState;
  stages: StageStep[];
  status: StreamStatus;
  brief: Brief | null;
  error: string | null;
  elapsedMs: number | null;
  start: (query: string) => Promise<void>;
  stop: () => void;
  reset: () => void;
}

export function useBriefStream({
  endpoint,
}: UseBriefStreamOptions): UseBriefStreamResult {
  const [state, setState] = useState<BriefStreamState>(createInitialState);

  const stateRef = useRef(state);
  const frameRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timedOutRef = useRef(false);

  const scheduleFlush = useCallback(() => {
    if (frameRef.current !== null) return;

    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      setState(stateRef.current);
    });
  }, []);

  const flush = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    setState(stateRef.current);
  }, []);

  const clearWatchdog = useCallback(() => {
    if (watchdogRef.current !== null) {
      clearTimeout(watchdogRef.current);
      watchdogRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
      }
      if (watchdogRef.current !== null) {
        clearTimeout(watchdogRef.current);
      }
    };
  }, []);

  const start = useCallback(
    async (query: string) => {
      abortRef.current?.abort();
      clearWatchdog();
      timedOutRef.current = false;

      const controller = new AbortController();
      abortRef.current = controller;

      const initial = startRun(query);
      stateRef.current = initial;
      setState(initial);

      watchdogRef.current = setTimeout(() => {
        if (abortRef.current !== controller) return;
        timedOutRef.current = true;
        controller.abort();
      }, WATCHDOG_MS);

      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query }),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(await httpErrorMessage(response));
        }
        if (!response.body) {
          throw new Error("The API did not return a response stream.");
        }

        let receivedBrief = false;

        for await (const frame of readSSE(response.body, controller.signal)) {
          let payload: unknown;
          try {
            payload = JSON.parse(frame.data) as unknown;
          } catch {
            continue;
          }

          const eventName =
            frame.event ??
            (parseStageEvent(payload)
              ? "stage"
              : parseBrief(payload)
                ? "brief"
                : parseErrorMessage(payload)
                  ? "error"
                  : undefined);

          if (eventName === "stage") {
            const event = parseStageEvent(payload);
            if (!event) continue;
            stateRef.current = applyStage(stateRef.current, event);
            scheduleFlush();
            continue;
          }

          if (eventName === "brief") {
            const brief = parseBrief(payload);
            if (!brief) continue;
            stateRef.current = applyBrief(stateRef.current, brief);
            receivedBrief = true;
            flush();
            break;
          }

          if (eventName === "error") {
            throw new Error(parseErrorMessage(payload) ?? "The pipeline failed.");
          }
        }

        if (abortRef.current !== controller) return;

        if (!receivedBrief) {
          stateRef.current = finalizeWithoutBrief(stateRef.current);
          flush();
        }
      } catch (caught) {
        if (abortRef.current !== controller) return;

        if (controller.signal.aborted) {
          if (timedOutRef.current) {
            stateRef.current = applyError(
              stateRef.current,
              `The brief took longer than ${WATCHDOG_MS / 1000} seconds and was stopped.`,
            );
          } else {
            stateRef.current = markStopped(stateRef.current);
          }
          flush();
          return;
        }

        const message =
          caught instanceof Error ? caught.message : "The stream failed.";
        stateRef.current = applyError(stateRef.current, message);
        flush();
      } finally {
        if (abortRef.current === controller) {
          clearWatchdog();
          abortRef.current = null;
        }
      }
    },
    [endpoint, scheduleFlush, flush, clearWatchdog],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    clearWatchdog();

    if (stateRef.current.status !== "streaming") return;

    stateRef.current = markStopped(stateRef.current);
    flush();
  }, [clearWatchdog, flush]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    clearWatchdog();

    stateRef.current = createInitialState();
    flush();
  }, [clearWatchdog, flush]);

  const stages = deriveStages(state);
  const elapsedMs =
    state.startedAt !== null && state.endedAt !== null
      ? state.endedAt - state.startedAt
      : null;

  return {
    state,
    stages,
    status: state.status,
    brief: state.brief,
    error: state.error,
    elapsedMs,
    start,
    stop,
    reset,
  };
}

async function httpErrorMessage(response: Response): Promise<string> {
  const prefix = `The API returned HTTP ${response.status}.`;

  try {
    const payload: unknown = await response.json();
    if (isRecord(payload)) {
      const detail = payload.detail;
      if (typeof detail === "string" && detail.trim()) {
        return `${prefix} ${detail}`;
      }
      if (Array.isArray(detail) && detail.length > 0) {
        const first: unknown = detail[0];
        if (isRecord(first) && typeof first.msg === "string") {
          return `${prefix} ${first.msg}`;
        }
      }
    }
  } catch {
    return prefix;
  }

  return prefix;
}
