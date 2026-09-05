import type {
  ActivityEvent,
  ExecutionState,
  TurnEvent,
  TurnStatus,
} from "./types";

const STATUS_LABELS: Record<TurnStatus, string> = {
  idle: "准备就绪",
  queued: "等待调度",
  running: "执行中",
  waiting_approval: "等待审批",
  completed: "已完成",
  failed: "执行失败",
  interrupted: "已中断",
  cancelled: "已取消",
};

const TERMINAL_STATUSES = new Set<TurnStatus>([
  "completed",
  "failed",
  "interrupted",
  "cancelled",
]);

/** 创建尚未收到任何 Turn 事件的执行状态。 */
export function createExecutionState(): ExecutionState {
  return {
    turnId: "",
    status: "idle",
    statusLabel: STATUS_LABELS.idle,
    answer: "",
    totalTokens: null,
    lastSequence: 0,
    events: [],
    error: "",
  };
}

/** 判断 Turn 是否已经进入不会继续执行的终态。 */
export function isTerminalStatus(status: TurnStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

/** 按单调序号把一个公开事件归约到当前执行状态。 */
export function reduceTurnEvent(
  state: ExecutionState,
  event: TurnEvent,
): ExecutionState {
  if (event.sequence <= state.lastSequence || isTerminalStatus(state.status)) {
    return state;
  }

  const next = {
    ...state,
    turnId: event.turn_id ?? state.turnId,
    lastSequence: event.sequence,
    events: [...state.events, toActivityEvent(event)],
  };
  const turnStatus = statusFromEventType(event.type);
  if (turnStatus) {
    next.status = turnStatus;
    next.statusLabel = STATUS_LABELS[turnStatus];
  }

  const item = getRecord(event.payload.item);
  const itemPayload = getRecord(item?.payload);
  if (event.type === "item.in_progress" && item?.type === "agent_message") {
    next.answer += getString(itemPayload?.delta);
  }
  if (event.type === "item.completed" && item?.type === "agent_message") {
    next.answer = getString(itemPayload?.answer) || next.answer;
    next.totalTokens = getNumber(getRecord(itemPayload?.usage)?.total_tokens);
  }
  if (event.type === "item.failed") {
    next.error =
      getString(itemPayload?.message) ||
      getString(itemPayload?.code) ||
      "任务执行失败。";
    next.status = "failed";
    next.statusLabel = STATUS_LABELS.failed;
  }
  return next;
}

/** 把协议事件转换为检查器需要的稳定展示结构。 */
function toActivityEvent(event: TurnEvent): ActivityEvent {
  const item = getRecord(event.payload.item);
  const itemPayload = getRecord(item?.payload);
  const definitions: Record<
    string,
    Pick<ActivityEvent, "title" | "tone">
  > = {
    "turn.queued": { title: "Turn 已创建", tone: "neutral" },
    "turn.running": { title: "Runtime 开始执行", tone: "progress" },
    "turn.waiting_approval": { title: "等待用户审批", tone: "progress" },
    "turn.completed": { title: "Turn 已完成", tone: "success" },
    "turn.failed": { title: "Turn 执行失败", tone: "danger" },
    "turn.interrupted": { title: "Turn 已中断", tone: "danger" },
    "turn.cancelled": { title: "Turn 已取消", tone: "danger" },
    "item.in_progress": { title: "模型正在生成", tone: "progress" },
    "item.completed": { title: "执行项已完成", tone: "success" },
    "item.failed": { title: "执行项失败", tone: "danger" },
  };
  const definition = definitions[event.type] ?? {
    title: event.type,
    tone: "neutral" as const,
  };
  const detail =
    getString(itemPayload?.message) ||
    getString(itemPayload?.finish_reason) ||
    getString(item?.type) ||
    "";
  return {
    sequence: event.sequence,
    type: event.type,
    title: definition.title,
    detail,
    occurredAt: event.occurred_at,
    tone: definition.tone,
    payload: {},
  };
}

/** 从 `turn.*` 事件名提取已知状态，未知值保持原状态。 */
function statusFromEventType(type: string): TurnStatus | null {
  if (!type.startsWith("turn.")) {
    return null;
  }
  const status = type.slice(5);
  return Object.hasOwn(STATUS_LABELS, status) ? (status as TurnStatus) : null;
}

/** 在协议边界把未知值收窄为普通对象。 */
function getRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/** 在协议边界安全读取字符串，避免组件猜测动态 JSON。 */
function getString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** 在协议边界安全读取数值，缺失时返回空值。 */
function getNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
