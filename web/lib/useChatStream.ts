"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { Brief } from "@/app/types";
import {
  appendToken,
  applyBriefEvent,
  applyStageEvent,
  applyToolEvent,
  createChatState,
  failTurn,
  finishTurn,
  markHydrated,
  parseChatConversation,
  parseChatTurn,
  restoredChatState,
  selectBrief as selectBriefState,
  setConversationId,
  startTurn,
  stopTurn,
  type ChatState,
  type ChatToolState,
} from "./chat-state";
import { readSSE } from "./sse";
import {
  deriveStages,
  isRecord,
  parseBrief,
  parseErrorMessage,
  parseStageEvent,
  type StageStep,
} from "./stream-state";

const WATCHDOG_MS = 240_000;
const STORAGE_KEY = "newsagreator.conversation";

export interface UseChatStreamOptions {
  endpoint: string;
  conversationsEndpoint: string;
}

export interface UseChatStreamResult {
  state: ChatState;
  stages: StageStep[];
  elapsedMs: number | null;
  send: (message: string) => Promise<void>;
  stop: () => void;
  reset: () => void;
  selectBrief: (brief: Brief) => void;
}

export function useChatStream({
  endpoint,
  conversationsEndpoint,
}: UseChatStreamOptions): UseChatStreamResult {
  const [state, setState] = useState<ChatState>(createChatState);

  const stateRef = useRef(state);
  const frameRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timedOutRef = useRef(false);
  const hydratedRef = useRef(false);

  const flush = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    setState(stateRef.current);
  }, []);

  const scheduleFlush = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      setState(stateRef.current);
    });
  }, []);

  const apply = useCallback(
    (next: ChatState, immediate = false) => {
      stateRef.current = next;
      if (immediate) flush();
      else scheduleFlush();
    },
    [flush, scheduleFlush],
  );

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
      clearWatchdog();
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
      }
    };
  }, [clearWatchdog]);

  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;

    const conversationId = readConversationId();
    if (!conversationId) {
      apply(markHydrated(stateRef.current), true);
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch(
          `${conversationsEndpoint}/${conversationId}`,
        );
        if (cancelled) return;
        if (response.status === 404) {
          clearStoredConversationId();
          apply(markHydrated(stateRef.current), true);
          return;
        }
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload: unknown = await response.json();
        const conversation = parseChatConversation(payload);
        if (!conversation) {
          clearStoredConversationId();
          apply(markHydrated(stateRef.current), true);
          return;
        }
        apply(restoredChatState(conversation), true);
      } catch {
        if (!cancelled) apply(markHydrated(stateRef.current), true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [apply, conversationsEndpoint]);

  const send = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      const current = stateRef.current;
      if (!trimmed || current.phase === "executing") return;

      abortRef.current?.abort();
      clearWatchdog();
      timedOutRef.current = false;

      const controller = new AbortController();
      abortRef.current = controller;
      apply(startTurn(current, trimmed), true);

      watchdogRef.current = setTimeout(() => {
        if (abortRef.current !== controller) return;
        timedOutRef.current = true;
        controller.abort();
      }, WATCHDOG_MS);

      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            conversation_id: stateRef.current.conversationId,
            message: trimmed,
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(await httpErrorMessage(response));
        }
        if (!response.body) {
          throw new Error("The API did not return a response stream.");
        }

        let finished = false;

        for await (const frame of readSSE(response.body, controller.signal)) {
          let payload: unknown;
          try {
            payload = JSON.parse(frame.data) as unknown;
          } catch {
            continue;
          }

          if (frame.event === "conversation") {
            if (
              isRecord(payload) &&
              typeof payload.conversation_id === "string"
            ) {
              storeConversationId(payload.conversation_id);
              apply(
                setConversationId(stateRef.current, payload.conversation_id),
                true,
              );
            }
            continue;
          }

          if (frame.event === "tool") {
            const tool = parseTool(payload);
            if (tool) apply(applyToolEvent(stateRef.current, tool));
            continue;
          }

          if (frame.event === "stage") {
            const event = parseStageEvent(payload);
            if (!event) continue;
            apply(applyStageEvent(stateRef.current, event));
            continue;
          }

          if (frame.event === "brief") {
            const brief = parseBrief(payload);
            if (!brief) continue;
            apply(applyBriefEvent(stateRef.current, brief), true);
            continue;
          }

          if (frame.event === "token") {
            if (isRecord(payload) && typeof payload.delta === "string") {
              apply(appendToken(stateRef.current, payload.delta));
            }
            continue;
          }

          if (frame.event === "chat") {
            const turn = parseChatTurn(payload);
            if (!turn) continue;
            storeConversationId(turn.conversation_id);
            apply(finishTurn(stateRef.current, turn), true);
            finished = true;
            break;
          }

          if (frame.event === "error") {
            throw new Error(
              parseErrorMessage(payload) ?? "The chat failed.",
            );
          }
        }

        if (abortRef.current !== controller) return;

        if (!finished) {
          apply(
            failTurn(
              stateRef.current,
              "The stream ended before a reply was ready.",
            ),
            true,
          );
        }
      } catch (caught) {
        if (abortRef.current !== controller) return;

        if (controller.signal.aborted) {
          if (timedOutRef.current) {
            apply(
              failTurn(
                stateRef.current,
                `The reply took longer than ${WATCHDOG_MS / 1000} seconds and was stopped.`,
              ),
              true,
            );
          } else {
            apply(stopTurn(stateRef.current), true);
          }
          return;
        }

        const message =
          caught instanceof Error ? caught.message : "The stream failed.";
        apply(failTurn(stateRef.current, message), true);
      } finally {
        if (abortRef.current === controller) {
          clearWatchdog();
          abortRef.current = null;
        }
      }
    },
    [apply, clearWatchdog, endpoint],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    clearWatchdog();

    if (stateRef.current.phase !== "executing") return;
    apply(stopTurn(stateRef.current), true);
  }, [apply, clearWatchdog]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    clearWatchdog();

    const conversationId = stateRef.current.conversationId;
    if (conversationId) {
      void fetch(`${conversationsEndpoint}/${conversationId}`, {
        method: "DELETE",
      }).catch(() => undefined);
    }
    clearStoredConversationId();
    apply({ ...createChatState(), hydrated: true }, true);
  }, [apply, clearWatchdog, conversationsEndpoint]);

  const selectBrief = useCallback(
    (brief: Brief) => {
      apply(selectBriefState(stateRef.current, brief), true);
    },
    [apply],
  );

  const stages = state.activeRun ? deriveStages(state.activeRun) : [];
  const elapsedMs =
    state.activeRun?.startedAt != null && state.activeRun.endedAt != null
      ? state.activeRun.endedAt - state.activeRun.startedAt
      : null;

  return {
    state,
    stages,
    elapsedMs,
    send,
    stop,
    reset,
    selectBrief,
  };
}

function parseTool(value: unknown): ChatToolState | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.name !== "string" ||
    typeof value.query !== "string" ||
    typeof value.status !== "string"
  ) {
    return null;
  }
  const status =
    value.status === "started" ||
    value.status === "completed" ||
    value.status === "failed"
      ? value.status
      : "started";
  return { name: value.name, query: value.query, status };
}

function storeConversationId(conversationId: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, conversationId);
  } catch {
    // Storage can be unavailable in private or restricted contexts.
  }
}

function readConversationId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function clearStoredConversationId(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage can be unavailable in private or restricted contexts.
  }
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
