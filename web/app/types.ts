export interface Candidate {
  title: string;
  url: string;
  publisher: string | null;
  domain: string | null;
  snippet: string | null;
  published_at: string | null;
  backend: string;
  tier: string;
  family: string | null;
  article_type: string | null;
  relevance: number | null;
  score: number | null;
  needs_resolution: boolean;
}

export interface Article {
  candidate: Candidate;
  canonical_url: string;
  resolved_publisher: string | null;
  word_count: number | null;
  text_status: string;
  fetched_at: string | null;
}

export interface Fact {
  claim: string;
  value: string | null;
  source_url: string;
  published_at: string;
  quote: string | null;
  cluster_id: string | null;
  confidence: number | null;
}

export interface Importance {
  score: number;
  severity: number;
  tier: number;
  corroboration: number;
  recency: number;
}

export interface Credibility {
  score: number;
  tier: number;
  propaganda_risk: number;
  corroboration: number;
  capped: boolean;
}

export interface Story {
  id: string;
  headline: string;
  members: Article[];
  families: string[];
  importance: Importance;
  credibility: Credibility;
  facts: Fact[];
  first_seen: string | null;
  last_seen: string | null;
}

export interface FactRow {
  value: string;
  meaning: string;
  source_url: string;
  published_at: string;
}

export interface TimelineEntry {
  at: string;
  what: string;
  source_url: string;
}

export interface Position {
  claim: string;
  source_url: string;
  published_at: string;
}

export interface Disagreement {
  topic: string;
  positions: Position[];
}

export interface BackendCoverage {
  backend: string;
  attempted: number;
  returned: number;
  kept: number;
  drops: Record<string, number>;
}

export interface BackendAttempt {
  backend: string;
  attempt: string;
  returned: number;
  elapsed_ms: number;
  detail: string | null;
}

export interface Coverage {
  status: string;
  backends: BackendCoverage[];
  attempts: BackendAttempt[];
  drops: Record<string, number>;
  text_status: Record<string, number>;
  timings_ms: Record<string, number>;
  notes: string[];
}

export type ChartKind = "bar" | "line" | "pie";
export type ChartValueFormat = "number" | "duration" | "percent";

export interface ChartPoint {
  label: string;
  value: number;
  at: string | null;
}

export interface ChartSeries {
  label: string;
  points: ChartPoint[];
}

export interface ChartSpec {
  kind: ChartKind;
  title: string;
  subtitle: string | null;
  takeaway: string | null;
  value_format: ChartValueFormat;
  value_suffix: string | null;
  series: ChartSeries[];
}

export interface MapPoint {
  country_code: string;
  country: string;
  label: string;
  lat: number;
  lon: number;
  story_ids: string[];
  summary: string | null;
}

export interface MapData {
  points: MapPoint[];
}

export interface Brief {
  query: string;
  query_class: string;
  answer: string;
  key_facts: FactRow[];
  timeline: TimelineEntry[];
  disagreements: Disagreement[];
  thin_sourcing: string[];
  stories: Story[];
  coverage: Coverage;
  generated_at: string;
  charts?: ChartSpec[];
  map?: MapData | null;
}

export interface StageEvent {
  stage: string;
  state: string;
  counts: Record<string, number>;
  message: string | null;
  elapsed_ms: number | null;
  at: string;
}

export type ChatRole = "user" | "assistant";

export interface ChatRun {
  query: string;
  status: "completed" | "failed" | "stopped";
  elapsed_ms: number;
  stages: StageEvent[];
  coverage_status: string | null;
  story_count: number | null;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  created_at: string;
  brief?: Brief | null;
  run?: ChatRun | null;
}

export interface ChatTurn {
  conversation_id: string;
  user: ChatMessage;
  assistant: ChatMessage;
}

export interface ChatConversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
}
