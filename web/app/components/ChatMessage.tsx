"use client";

import type { Brief, ChatMessage as ChatMessageModel } from "@/app/types";
import { BriefDetails } from "./BriefDetails";
import { ResultsPane } from "./ResultsPane";
import { RunSummary } from "./RunSummary";

interface ChatMessageProps {
  message: ChatMessageModel;
  selectedBrief: Brief | null;
  onSelectBrief: (brief: Brief) => void;
}

export function ChatMessage({
  message,
  selectedBrief,
  onSelectBrief,
}: ChatMessageProps) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap rounded-card border border-line bg-surface px-4 py-3 text-[15px] leading-6 text-ink">
          {message.content}
        </p>
      </div>
    );
  }

  const viewing = Boolean(
    message.brief && selectedBrief === message.brief,
  );

  return (
    <div className="max-w-[68ch]">
      <p className="whitespace-pre-wrap text-[17px] leading-[1.65] text-ink">
        {message.content}
      </p>

      {message.run ? <RunSummary run={message.run} /> : null}

      {message.brief ? (
        <>
          {!viewing ? (
            <button
              type="button"
              onClick={() => onSelectBrief(message.brief as Brief)}
              className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-accent transition-colors hover:text-accent-strong"
            >
              View results
              <span aria-hidden="true">→</span>
            </button>
          ) : null}
          <BriefDetails brief={message.brief} />
          <div className="mt-4 lg:hidden">
            <div className="overflow-hidden rounded-card border border-line">
              <ResultsPane brief={message.brief} />
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
