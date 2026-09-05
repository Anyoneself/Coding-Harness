import type { ChatMessage, ChatThread, MessageRole } from "./types";

export const CHAT_LIMIT = 30;
export const CHAT_STORAGE_KEY = "coding-harness-threads-v1";
export const ACTIVE_CHAT_KEY = `${CHAT_STORAGE_KEY}:active`;
export const WORKSPACE_STORAGE_KEY = `${CHAT_STORAGE_KEY}:workspace`;
const SENSITIVE_FIELD_NAMES = new Set([
  "api_key",
  "apikey",
  "reasoning_content",
  "stack",
  "traceback",
]);

/** 创建一个尚未绑定服务端 Thread 的本地任务。 */
export function createChat(id: string = crypto.randomUUID()): ChatThread {
  return {
    id,
    threadId: "",
    title: "新任务",
    status: "等待输入",
    updatedAt: Date.now(),
    messages: [],
  };
}

/** 创建可持久化的公开消息，不接收密钥或内部错误对象。 */
export function createMessage(
  role: MessageRole,
  content: string,
  isError = false,
): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    createdAt: Date.now(),
    ...(isError ? { isError: true } : {}),
  };
}

/** 按最近更新时间排序，并限制浏览器持久化的任务数量。 */
export function sortAndLimitChats(chats: ChatThread[]): ChatThread[] {
  return [...chats]
    .sort((left, right) => right.updatedAt - left.updatedAt)
    .slice(0, CHAT_LIMIT);
}

/** 按 Unicode 字符生成最多 32 字符的本地任务标题。 */
export function normalizeChatTitle(message: string): string {
  return Array.from(message.trim()).slice(0, 32).join("") || "新任务";
}

/** 从不可信 JSON 中读取结构完整的公开任务数据。 */
export function loadStoredChats(raw: string | null): ChatThread[] {
  if (!raw) {
    return [];
  }
  try {
    const value: unknown = JSON.parse(raw);
    if (!Array.isArray(value)) {
      return [];
    }
    return sortAndLimitChats(
      value
        .map(normalizeStoredChat)
        .filter((chat): chat is ChatThread => chat !== null),
    );
  } catch {
    return [];
  }
}

/** 归一化当前和旧版 localStorage 任务，补齐纯展示字段。 */
function normalizeStoredChat(value: unknown): ChatThread | null {
  if (!isRecord(value) || containsSensitiveField(value)) {
    return null;
  }
  const isValid =
    typeof value.id === "string" &&
    typeof value.threadId === "string" &&
    typeof value.title === "string" &&
    typeof value.status === "string" &&
    typeof value.updatedAt === "number" &&
    Array.isArray(value.messages);
  if (!isValid) {
    return null;
  }
  const storedMessages = value.messages as unknown[];
  const messages = storedMessages
    .map((message) => normalizeStoredMessage(message, value.updatedAt as number))
    .filter((message): message is ChatMessage => message !== null);
  if (messages.length !== storedMessages.length) {
    return null;
  }
  return {
    id: value.id as string,
    threadId: value.threadId as string,
    title: value.title as string,
    status: value.status as string,
    updatedAt: value.updatedAt as number,
    messages,
  };
}

/** 递归识别不允许进入本地公开历史的敏感字段。 */
function containsSensitiveField(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.some(containsSensitiveField);
  }
  if (!isRecord(value)) {
    return false;
  }
  return Object.entries(value).some(
    ([key, nestedValue]) =>
      SENSITIVE_FIELD_NAMES.has(key.toLowerCase()) ||
      containsSensitiveField(nestedValue),
  );
}

/** 归一化公开消息，并兼容旧版缺少 ID 与时间的结构。 */
function normalizeStoredMessage(
  value: unknown,
  fallbackTimestamp: number,
): ChatMessage | null {
  if (
    !isRecord(value) ||
    (value.role !== "user" && value.role !== "assistant") ||
    typeof value.content !== "string" ||
    (value.isError !== undefined && typeof value.isError !== "boolean")
  ) {
    return null;
  }
  return {
    id: typeof value.id === "string" ? value.id : crypto.randomUUID(),
    role: value.role,
    content: value.content,
    createdAt:
      typeof value.createdAt === "number" ? value.createdAt : fallbackTimestamp,
    ...(value.isError ? { isError: true } : {}),
  };
}

/** 判断未知值是否为普通键值对象。 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 按本地时间把历史任务归入易扫描的日期组。 */
export function historyGroup(updatedAt: number, now = new Date()): string {
  const date = new Date(updatedAt);
  if (date.toDateString() === now.toDateString()) {
    return "今天";
  }
  if (now.getTime() - date.getTime() < 7 * 86_400_000) {
    return "最近 7 天";
  }
  return "更早";
}
