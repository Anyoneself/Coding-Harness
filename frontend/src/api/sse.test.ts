import { describe, expect, it } from "vitest";

import { createSseParser } from "./sse";

describe("SSE 分块解析", () => {
  it("跨网络分块拼接 data 并保留尾部缓存", () => {
    /** 验证拆分到任意边界的 SSE 仍返回完整公开事件。 */
    const events: unknown[] = [];
    const parser = createSseParser((event) => events.push(event));

    parser.push('id: 1\nevent: turn.running\ndata: {"type":"turn.');
    parser.push('running","sequence":1,"payload":{}}\n\n');

    expect(events).toEqual([
      { type: "turn.running", sequence: 1, payload: {} },
    ]);
  });

  it("忽略没有 JSON data 的心跳块", () => {
    /** 验证注释和空事件不会触发状态归约。 */
    const events: unknown[] = [];
    const parser = createSseParser((event) => events.push(event));

    parser.push(": keep-alive\n\n");

    expect(events).toEqual([]);
  });

  it("解析多行 data 与没有空行结尾的尾块", () => {
    /** 验证符合 SSE 规范的多行数据可以在 flush 时完成解析。 */
    const events: unknown[] = [];
    const parser = createSseParser((event) => events.push(event));

    parser.push('data: {"type":"turn.running",\ndata: "sequence":2,"payload":{}}');
    parser.flush();

    expect(events).toEqual([
      { type: "turn.running", sequence: 2, payload: {} },
    ]);
  });

  it("忽略畸形 JSON 并继续解析后续公开事件", () => {
    /** 验证单个不可信事件不会终止整个公开事件流。 */
    const events: unknown[] = [];
    const parser = createSseParser((event) => events.push(event));

    parser.push("data: {not-json}\n\n");
    parser.push('data: {"type":"future.event","sequence":3,"payload":{}}\n\n');

    expect(events).toEqual([
      { type: "future.event", sequence: 3, payload: {} },
    ]);
  });
});
