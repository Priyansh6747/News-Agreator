import type {
  Brief,
  ChatConversation,
  ChatMessage,
  ChatRun,
  ChatTurn,
  StageEvent,
} from "@/app/types";
import {
  applyBrief,
  applyError,
  applyStage,
  createInitialState,
  deriveStages,
  isRecord,
  markStopped,
  parseBrief,
  parseStageEvent,
  startRun,
  type BriefStreamState,
  type StageName,
  type StageEventPayload,
  type StageRecord,
  type StageStep,
} from "./stream-state";

export type ChatPhase = "idle" | "executing" | "results";

export interface ChatToolState {
  name: string;
  query: string;
  status: "started" | "completed" | "failed";
}

export interface ChatState {
  phase: ChatPhase;
  conversationId: string | null;
  messages: ChatMessage[];
  activeRun: BriefStreamState | null;
  activeTool: ChatToolState | null;
  pendingAssistant: string;
  selectedBrief: Brief | null;
  error: string | null;
  hydrated: boolean;
}

export function createChatState(): ChatState {
  return {
    phase: "idle",
    conversationId: null,
    messages: [],
    activeRun: null,
    activeTool: null,
    pendingAssistant: "",
    selectedBrief: null,
    error: null,
    hydrated: false,
  };
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `m_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

export function startTurn(
  state: ChatState,
  message: string,
  now = Date.now(),
): ChatState {
  const user: ChatMessage = {
    id: newId(),
    role: "user",
    content: message,
    created_at: new Date(now).toISOString(),
  };
  return {
    ...state,
    phase: "executing",
    messages: [...state.messages, user],
    activeRun: startRun(message, now),
    activeTool: null,
    pendingAssistant: "",
    error: null,
  };
}

export function applyStageEvent(
  state: ChatState,
  event: StageEventPayload,
): ChatState {
  if (!state.activeRun) return state;
  return { ...state, activeRun: applyStage(state.activeRun, event) };
}

export function applyToolEvent(
  state: ChatState,
  tool: ChatToolState,
): ChatState {
  return { ...state, activeTool: tool };
}

export function applyBriefEvent(state: ChatState, brief: Brief): ChatState {
  return {
    ...state,
    activeRun: state.activeRun
      ? applyBrief(state.activeRun, brief)
      : state.activeRun,
    selectedBrief: brief,
  };
}

export function appendToken(state: ChatState, delta: string): ChatState {
  return { ...state, pendingAssistant: state.pendingAssistant + delta };
}

export function finishTurn(state: ChatState, turn: ChatTurn): ChatState {
  const assistant = turn.assistant;
  return {
    ...state,
    phase: "results",
    conversationId: turn.conversation_id,
    messages: [...state.messages, assistant],
    activeRun: null,
    activeTool: null,
    pendingAssistant: "",
    selectedBrief: assistant.brief ?? state.selectedBrief,
    error: null,
  };
}

export function failTurn(state: ChatState, message: string): ChatState {
  return {
    ...state,
    phase: "results",
    activeRun: state.activeRun ? applyError(state.activeRun, message) : null,
    activeTool: null,
    pendingAssistant: "",
    error: message,
  };
}

export function stopTurn(state: ChatState, now = Date.now()): ChatState {
  const stopped = state.activeRun ? markStopped(state.activeRun, now) : null;
  const content =
    state.pendingAssistant.trim() ||
    "Stopped before the answer was ready.";
  const assistant: ChatMessage = {
    id: newId(),
    role: "assistant",
    content,
    created_at: new Date(now).toISOString(),
    brief: stopped?.brief ?? null,
    run: stopped ? runFromState(stopped) : null,
  };
  return {
    ...state,
    phase: "results",
    messages: [...state.messages, assistant],
    activeRun: null,
    activeTool: null,
    pendingAssistant: "",
    selectedBrief: assistant.brief ?? state.selectedBrief,
  };
}

export function selectBrief(state: ChatState, brief: Brief): ChatState {
  return { ...state, selectedBrief: brief };
}

export function setConversationId(
  state: ChatState,
  conversationId: string,
): ChatState {
  return { ...state, conversationId };
}

export function markHydrated(state: ChatState): ChatState {
  return { ...state, hydrated: true };
}

export function restoredChatState(
  conversation: ChatConversation,
): ChatState {
  const lastBrief =
    [...conversation.messages].reverse().find((message) => message.brief)
      ?.brief ?? null;
  return {
    ...createChatState(),
    hydrated: true,
    conversationId: conversation.id,
    messages: conversation.messages,
    phase: conversation.messages.length > 0 ? "results" : "idle",
    selectedBrief: lastBrief,
  };
}

export function runFromState(state: BriefStreamState): ChatRun {
  const records = Object.values(state.stages).filter(
    (record): record is StageRecord => Boolean(record),
  );
  const stages: StageEvent[] = records.map((record) => ({
    stage: record.stage,
    state: record.state,
    counts: record.counts,
    message: record.message,
    elapsed_ms: record.elapsed_ms,
    at: record.at,
  }));
  return {
    query: state.query ?? "",
    status:
      state.status === "error"
        ? "failed"
        : state.status === "streaming"
          ? "stopped"
          : "completed",
    elapsed_ms:
      state.startedAt !== null && state.endedAt !== null
        ? state.endedAt - state.startedAt
        : 0,
    stages,
    coverage_status: state.brief?.coverage.status ?? null,
    story_count: state.brief?.stories.length ?? null,
  };
}

export function stagesFromEvents(events: StageEvent[]): StageStep[] {
  const stages: Partial<Record<StageName, StageRecord>> = {};
  for (const raw of events) {
    const event = parseStageEvent(raw);
    if (!event) continue;
    const previous = stages[event.stage];
    stages[event.stage] = {
      ...event,
      startedAt: previous?.startedAt ?? event.at,
    };
  }
  const state: BriefStreamState = {
    ...createInitialState(),
    status: "done",
    stages,
  };
  return deriveStages(state);
}

export function parseChatRun(value: unknown): ChatRun | null {
  if (!isRecord(value)) return null;
  if (typeof value.query !== "string") return null;
  if (typeof value.status !== "string") return null;
  if (typeof value.elapsed_ms !== "number") return null;
  if (!Array.isArray(value.stages)) return null;

  const stages = value.stages
    .map(parseStageEvent)
    .filter((event): event is StageEventPayload => Boolean(event));

  return {
    query: value.query,
    status:
      value.status === "failed" || value.status === "stopped"
        ? value.status
        : "completed",
    elapsed_ms: value.elapsed_ms,
    stages: stages as StageEvent[],
    coverage_status:
      typeof value.coverage_status === "string"
        ? value.coverage_status
        : null,
    story_count:
      typeof value.story_count === "number" ? value.story_count : null,
  };
}

export function parseChatMessage(value: unknown): ChatMessage | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.id !== "string" ||
    typeof value.content !== "string" ||
    typeof value.created_at !== "string"
  ) {
    return null;
  }
  const role =
    value.role === "assistant"
      ? "assistant"
      : value.role === "user"
        ? "user"
        : null;
  if (role === null) return null;

  let brief: Brief | null = null;
  if (value.brief != null) {
    brief = parseBrief(value.brief);
    if (brief === null) return null;
  }

  let run: ChatRun | null = null;
  if (value.run != null) {
    run = parseChatRun(value.run);
    if (run === null) return null;
  }

  return {
    id: value.id,
    role,
    content: value.content,
    created_at: value.created_at,
    brief,
    run,
  };
}

export function parseChatTurn(value: unknown): ChatTurn | null {
  if (!isRecord(value) || typeof value.conversation_id !== "string") {
    return null;
  }
  const user = parseChatMessage(value.user);
  const assistant = parseChatMessage(value.assistant);
  if (!user || !assistant) return null;
  return { conversation_id: value.conversation_id, user, assistant };
}

export function parseChatConversation(value: unknown): ChatConversation | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.id !== "string" ||
    typeof value.title !== "string" ||
    typeof value.created_at !== "string" ||
    typeof value.updated_at !== "string" ||
    !Array.isArray(value.messages)
  ) {
    return null;
  }
  const messages = value.messages.map(parseChatMessage);
  if (messages.some((message) => message === null)) return null;
  return {
    id: value.id,
    title: value.title,
    messages: messages as ChatMessage[],
    created_at: value.created_at,
    updated_at: value.updated_at,
  };
}
