import type { TurnEvent } from "../domain/types";

export interface SseParser {
  push(chunk: string): void;
  flush(): void;
}

/** 创建可以跨网络分块解析标准 SSE data 字段的增量解析器。 */
export function createSseParser(onEvent: (event: TurnEvent) => void): SseParser {
  let buffer = "";

  /** 解析一个已经包含完整分隔符的 SSE 事件块。 */
  function parseBlock(block: string): void {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) {
      return;
    }
    try {
      const value: unknown = JSON.parse(data);
      if (isTurnEvent(value)) {
        onEvent(value);
      }
    } catch {
      return;
    }
  }

  return {
    push(chunk: string): void {
      buffer += chunk.replace(/\r\n/g, "\n");
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      blocks.forEach(parseBlock);
    },
    flush(): void {
      if (buffer.trim()) {
        parseBlock(buffer);
      }
      buffer = "";
    },
  };
}

/** 验证动态 SSE JSON 具备客户端归约所需的最小字段。 */
function isTurnEvent(value: unknown): value is TurnEvent {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const event = value as Record<string, unknown>;
  return (
    typeof event.type === "string" &&
    typeof event.sequence === "number" &&
    typeof event.payload === "object" &&
    event.payload !== null &&
    !Array.isArray(event.payload)
  );
}
