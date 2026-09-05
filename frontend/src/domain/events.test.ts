import { describe, expect, it } from "vitest";

import {
  createExecutionState,
  isTerminalStatus,
  reduceTurnEvent,
} from "./events";

describe("Turn 事件归约", () => {
  it("拒绝重复和倒序事件，避免重复追加文本", () => {
    /** 验证序号是客户端归约公开事件的唯一推进依据。 */
    const running = reduceTurnEvent(createExecutionState(), {
      type: "item.in_progress",
      sequence: 2,
      turn_id: "turn-1",
      payload: {
        item: { type: "agent_message", payload: { delta: "完成" } },
      },
    });

    const duplicated = reduceTurnEvent(running, {
      type: "item.in_progress",
      sequence: 2,
      turn_id: "turn-1",
      payload: {
        item: { type: "agent_message", payload: { delta: "完成" } },
      },
    });

    expect(duplicated.answer).toBe("完成");
    expect(duplicated.events).toHaveLength(1);
  });

  it("最终消息收敛流式文本并进入完成状态", () => {
    /** 验证完成事件覆盖不完整增量并公开用量。 */
    const partial = reduceTurnEvent(createExecutionState(), {
      type: "item.in_progress",
      sequence: 1,
      turn_id: "turn-1",
      payload: {
        item: { type: "agent_message", payload: { delta: "半成" } },
      },
    });
    const completed = reduceTurnEvent(partial, {
      type: "item.completed",
      sequence: 2,
      turn_id: "turn-1",
      payload: {
        item: {
          type: "agent_message",
          payload: { answer: "完整回答", usage: { total_tokens: 42 } },
        },
      },
    });
    const terminal = reduceTurnEvent(completed, {
      type: "turn.completed",
      sequence: 3,
      turn_id: "turn-1",
      payload: {},
    });

    expect(terminal.answer).toBe("完整回答");
    expect(terminal.totalTokens).toBe(42);
    expect(terminal.status).toBe("completed");
  });

  it.each(["completed", "failed", "interrupted", "cancelled"] as const)(
    "把 %s 识别为 Turn 终态",
    (status) => {
      /** 验证事件流结束判定覆盖全部公开终态。 */
      expect(isTerminalStatus(status)).toBe(true);
    },
  );

  it("保留未知事件并维持当前状态", () => {
    /** 验证未来公开事件不会被丢弃或被猜测成已有状态。 */
    const state = reduceTurnEvent(createExecutionState(), {
      type: "tool.future_event",
      sequence: 1,
      payload: {},
    });

    expect(state.status).toBe("idle");
    expect(state.events[0]).toMatchObject({
      type: "tool.future_event",
      title: "tool.future_event",
    });
  });

  it("终态后忽略迟到事件，避免状态回退", () => {
    /** 验证已完成 Turn 不会被更晚的运行事件重新打开。 */
    const completed = reduceTurnEvent(createExecutionState(), {
      type: "turn.completed",
      sequence: 2,
      payload: {},
    });
    const late = reduceTurnEvent(completed, {
      type: "turn.running",
      sequence: 3,
      payload: {},
    });

    expect(late).toBe(completed);
    expect(late.status).toBe("completed");
  });

  it("只公开安全的失败提示", () => {
    /** 验证失败事件不会把嵌套响应、堆栈或隐藏推理带到界面。 */
    const failed = reduceTurnEvent(createExecutionState(), {
      type: "item.failed",
      sequence: 1,
      payload: {
        item: {
          type: "agent_message",
          payload: {
            message: "任务执行失败。",
            stack: "/Users/example/internal.py:10",
            reasoning_content: "hidden",
          },
        },
      },
    });

    expect(failed.error).toBe("任务执行失败。");
    expect(failed.events[0].payload).toEqual({});
  });
});
