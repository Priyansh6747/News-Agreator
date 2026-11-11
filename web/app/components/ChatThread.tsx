"use client";

import { useEffect, useRef } from "react";

import type { Brief, ChatMessage as ChatMessageModel } from "@/app/types";
import type { ChatToolState } from "@/lib/chat-state";
import type {
  BriefStreamState,
  StageStep,
  StreamStatus,
} from "@/lib/stream-state";
import { ChatMessage } from "./ChatMessage";
import { ExecutionPane } from "./ExecutionPane";
import { Orb } from "./Orb";
import { ResultsPane } from "./ResultsPane";

interface ChatThreadProps {
  messages: ChatMessageModel[];
  pendingAssistant: string;
  activeRun: BriefStreamState | null;
  activeTool: ChatToolState | null;
  stages: StageStep[];
  status: StreamStatus;
  elapsedMs: number | null;
  selectedBrief: Brief | null;
  onSelectBrief: (brief: Brief) => void;
  streaming: boolean;
}

export function ChatThread({
  messages,
  pendingAssistant,
  activeRun,
  activeTool,
  stages,
  status,
  elapsedMs,
  selectedBrief,
  onSelectBrief,
  streaming,
}: ChatThreadProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);

  useEffect(() => {
    if (!atBottomRef.current) return;
    const frame = requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ block: "end" });
    });
    return () => cancelAnimationFrame(frame);
  }, [messages.length, pendingAssistant, activeRun?.status, selectedBrief]);

  useEffect(() => {
    atBottomRef.current = true;
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, []);

  function handleScroll() {
    const element = containerRef.current;
    if (!element) return;
    const distance =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    atBottomRef.current = distance < 80;
  }

  const activeStage = stages.find((step) => step.state === "active");

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      role="log"
      aria-label="Conversation"
      className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6"
    >
      <div className="mx-auto flex max-w-[720px] flex-col gap-6">
        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            message={message}
            selectedBrief={selectedBrief}
            onSelectBrief={onSelectBrief}
          />
        ))}

        {streaming ? (
          <div className="max-w-[68ch]">
            {pendingAssistant ? (
              <p className="whitespace-pre-wrap text-[17px] leading-[1.65] text-ink">
                {pendingAssistant}
                <span
                  aria-hidden="true"
                  className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] animate-pulse bg-accent align-baseline"
                />
              </p>
            ) : (
              <div className="flex items-center gap-3">
                <Orb size="sm" />
                <p className="text-[13px] leading-5 text-ink-muted">
                  {activeStage
                    ? `${activeStage.label}...`
                    : activeRun
                      ? "Understanding your message..."
                      : "Working..."}
                </p>
              </div>
            )}
          </div>
        ) : null}

        {streaming && activeRun && !selectedBrief ? (
          <div className="lg:hidden">
            <div className="overflow-hidden rounded-card border border-line">
              <ExecutionPane
                query={activeTool?.query ?? activeRun.query ?? ""}
                stages={stages}
                status={status}
                elapsedMs={elapsedMs}
                storyCount={activeRun.brief?.stories.length ?? null}
                coverageStatus={activeRun.brief?.coverage.status ?? null}
                tool={activeTool}
              />
            </div>
          </div>
        ) : null}

        {streaming && selectedBrief ? (
          <div className="lg:hidden">
            <div className="overflow-hidden rounded-card border border-line">
              <ResultsPane brief={selectedBrief} />
            </div>
          </div>
        ) : null}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
