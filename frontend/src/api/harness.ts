import { createSseParser } from "./sse";
import type { PublicConfig, TurnEvent } from "../domain/types";

export class HttpError extends Error {
  /** 保存不会包含响应正文或敏感配置的 HTTP 状态。 */
  constructor(public readonly status: number) {
    super(`HTTP ${status}`);
    this.name = "HttpError";
  }
}

interface WorkspaceResponse {
  id: string;
}

interface ThreadResponse {
  id: string;
}

interface TurnResponse {
  id: string;
}

/** 读取 Harness 对前端公开的无敏感配置。 */
export function getPublicConfig(): Promise<PublicConfig> {
  return requestJson<PublicConfig>("/api/config");
}

/** 首次提交 API Key，调用方不得保存传入值。 */
export function configureApiKey(apiKey: string): Promise<{ ready: boolean }> {
  return requestJson("/api/config/api-key", {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey }),
  });
}

/** 创建绑定当前服务端工作目录的只读 Workspace。 */
export function createWorkspace(rootPath: string): Promise<WorkspaceResponse> {
  return requestJson("/api/workspaces", {
    method: "POST",
    body: JSON.stringify({
      root_path: rootPath,
      permission_profile: "read_only",
    }),
  });
}

/** 在指定 Workspace 下创建持续任务 Thread。 */
export function createThread(
  workspaceId: string,
  title: string,
): Promise<ThreadResponse> {
  return requestJson(`/api/workspaces/${workspaceId}/threads`, {
    method: "POST",
    body: JSON.stringify({ title: title.slice(0, 80) }),
  });
}

/** 创建一次后台 Turn，并立即返回稳定资源标识。 */
export function createTurn(
  threadId: string,
  prompt: string,
): Promise<TurnResponse> {
  return requestJson(`/api/threads/${threadId}/turns`, {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
}

/** 请求中断当前 Turn，实际终态以事件流为准。 */
export function interruptTurn(turnId: string): Promise<TurnResponse> {
  return requestJson(`/api/turns/${turnId}/interrupt`, { method: "POST" });
}

/** 持续读取公开 Turn 事件，直到服务端在终态关闭连接。 */
export async function streamTurnEvents(
  turnId: string,
  onEvent: (event: TurnEvent) => void,
): Promise<void> {
  const response = await fetch(
    `/api/turns/${turnId}/events/stream?after_sequence=0`,
  );
  if (!response.ok || !response.body) {
    throw new HttpError(response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSseParser(onEvent);
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    parser.push(decoder.decode(value, { stream: true }));
  }
  parser.push(decoder.decode());
  parser.flush();
}

/** 执行同源 JSON 请求，并把失败收敛为不含响应详情的错误。 */
async function requestJson<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  if (!response.ok) {
    throw new HttpError(response.status);
  }
  return (await response.json()) as T;
}
