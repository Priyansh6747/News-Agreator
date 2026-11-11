"use client";

import type { Brief, ChatMessage as ChatMessageModel } from "@/app/types";
import type { ChatState } from "@/lib/chat-state";
import type { StageStep, StreamStatus } from "@/lib/stream-state";
import type { ApiStatus } from "@/lib/useApiStatus";
import { ChatThread } from "./ChatThread";
import { Composer } from "./Composer";
import { CoveragePill } from "./CoveragePill";
import { ExecutionPane } from "./ExecutionPane";
import { Orb } from "./Orb";
import { ResultsPane } from "./ResultsPane";
import { TopBar } from "./TopBar";

interface ChatShellProps {
  state: ChatState;
  apiStatus: ApiStatus;
  input: string;
  onInput: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  onReset: () => void;
  onSelectBrief: (brief: Brief) => void;
  stages: StageStep[];
  elapsedMs: number | null;
  streaming: boolean;
}

export function ChatShell({
  state,
  apiStatus,
  input,
  onInput,
  onSend,
  onStop,
  onReset,
  onSelectBrief,
  stages,
  elapsedMs,
  streaming,
}: ChatShellProps) {
  const title =
    state.messages.find((message: ChatMessageModel) => message.role === "user")
      ?.content ?? "New conversation";

  const executionActive =
    state.activeRun !== null && state.activeRun.brief === null;
  const status: StreamStatus = state.activeRun?.status ?? "idle";
  const statusLine = state.error
    ? "The last turn did not finish."
    : streaming
      ? "Working through the sources..."
      : "Ready for a follow-up.";

  return (
    <main className="mx-auto flex h-dvh w-full max-w-[1440px] flex-col overflow-hidden lg:px-6">
      <div className="px-4 sm:px-8 lg:px-2">
        <TopBar apiStatus={apiStatus} compact onNewChat={onReset} />
      </div>

      <p role="status" aria-live="polite" className="sr-only">
        {state.error
          ? state.error
          : streaming
            ? "The assistant is working."
            : "The assistant is ready."}
      </p>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <section className="flex min-h-0 flex-col border-line lg:border-r">
          <header className="flex items-center gap-3 border-b border-line px-4 py-3 sm:px-6">
            <Orb size="sm" />
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-[18px] font-semibold tracking-[-0.02em] text-ink-strong">
                {title}
              </h1>
              <p className="mt-0.5 truncate text-[12px] leading-5 text-ink-muted">
                {statusLine}
              </p>
            </div>
            {state.selectedBrief ? (
              <CoveragePill status={state.selectedBrief.coverage.status} />
            ) : null}
          </header>

          <ChatThread
            messages={state.messages}
            pendingAssistant={state.pendingAssistant}
            activeRun={state.activeRun}
            activeTool={state.activeTool}
            stages={stages}
            status={status}
            elapsedMs={elapsedMs}
            selectedBrief={state.selectedBrief}
            onSelectBrief={onSelectBrief}
            streaming={streaming}
          />

          {state.error ? (
            <div
              role="alert"
              className="mx-4 mt-3 rounded-card border border-error/30 bg-error-soft px-4 py-3 text-[13px] leading-5 text-error sm:mx-6"
            >
              {state.error}
            </div>
          ) : null}

          <div className="shrink-0 border-t border-line bg-canvas/80 px-4 py-3 backdrop-blur sm:px-6">
            <Composer
              value={input}
              onChange={onInput}
              onSubmit={onSend}
              onStop={onStop}
              streaming={streaming}
              hasError={Boolean(state.error)}
              id="chat-query"
              compact
              minLength={1}
              maxLength={2000}
              submitLabel="Send message"
              stopLabel="Stop the response"
              placeholder="Ask a follow-up..."
            />
          </div>
        </section>

        <aside className="hidden min-h-0 overflow-y-auto border-line bg-canvas-soft/40 lg:block">
          {executionActive && state.activeRun ? (
            <ExecutionPane
              query={state.activeTool?.query ?? state.activeRun.query ?? ""}
              stages={stages}
              status={status}
              elapsedMs={elapsedMs}
              storyCount={state.activeRun.brief?.stories.length ?? null}
              coverageStatus={state.activeRun.brief?.coverage.status ?? null}
              tool={state.activeTool}
            />
          ) : state.selectedBrief ? (
            <ResultsPane brief={state.selectedBrief} />
          ) : (
            <div className="flex h-full items-center justify-center px-6 py-10 text-center">
              <div>
                <Orb size="md" />
                <p className="mt-4 text-[13px] leading-5 text-ink-muted">
                  Ask about a story to generate a brief.
                </p>
              </div>
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}
