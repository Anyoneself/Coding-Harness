export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: number;
  isError?: boolean;
}

export interface ChatThread {
  id: string;
  threadId: string;
  title: string;
  status: string;
  updatedAt: number;
  messages: ChatMessage[];
}

export interface PublicConfig {
  ready: boolean;
  model: string;
  workspace_root: string;
}

export type WorkbenchView = "workspace" | "events" | "turn";

export type TurnStatus =
  | "idle"
  | "queued"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "interrupted"
  | "cancelled";

export interface TurnEvent {
  type: string;
  sequence: number;
  turn_id?: string;
  thread_id?: string;
  workspace_id?: string;
  occurred_at?: string;
  payload: Record<string, unknown>;
}

export interface ActivityEvent {
  sequence: number;
  type: string;
  title: string;
  detail: string;
  occurredAt?: string;
  tone: "neutral" | "progress" | "success" | "danger";
  payload: Record<string, unknown>;
}

export interface ExecutionState {
  turnId: string;
  status: TurnStatus;
  statusLabel: string;
  answer: string;
  totalTokens: number | null;
  lastSequence: number;
  events: ActivityEvent[];
  error: string;
}
