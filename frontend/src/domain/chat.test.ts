import { describe, expect, it } from "vitest";

import {
  CHAT_LIMIT,
  createChat,
  historyGroup,
  loadStoredChats,
  normalizeChatTitle,
  sortAndLimitChats,
} from "./chat";

describe("Thread 本地持久化", () => {
  it("按更新时间排序并限制最近任务数量", () => {
    /** 验证超出上限的任务会被稳定裁剪。 */
    const chats = Array.from({ length: CHAT_LIMIT + 4 }, (_, index) => ({
      ...createChat(`chat-${index}`),
      updatedAt: index,
    }));

    const result = sortAndLimitChats(chats);

    expect(result).toHaveLength(CHAT_LIMIT);
    expect(result[0].id).toBe(`chat-${CHAT_LIMIT + 3}`);
  });

  it("忽略结构不合法和可能包含敏感字段的持久化数据", () => {
    /** 验证浏览器脏数据不会进入应用状态。 */
    const stored = JSON.stringify([
      {
        id: "valid",
        threadId: "",
        title: "架构检查",
        status: "已完成",
        updatedAt: 10,
        messages: [{ role: "user", content: "检查架构" }],
      },
      { id: "secret", apiKey: "sk-do-not-load" },
      null,
    ]);

    const result = loadStoredChats(stored);

    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("valid");
    expect(JSON.stringify(result)).not.toContain("sk-do-not-load");
  });

  it("拒绝消息内部包含敏感字段的任务记录", () => {
    /** 验证敏感字段无论嵌套层级都不会进入浏览器任务历史。 */
    const stored = JSON.stringify([
      {
        id: "secret",
        threadId: "thread-secret",
        title: "不可信任务",
        status: "已完成",
        updatedAt: 10,
        messages: [
          {
            role: "assistant",
            content: "公开内容",
            metadata: { apiKey: "sk-do-not-load" },
          },
        ],
      },
    ]);

    expect(loadStoredChats(stored)).toEqual([]);
  });

  it("按 Unicode 字符生成稳定的长任务标题", () => {
    /** 验证多字节字符标题不会在代理对中间截断。 */
    const title = normalizeChatTitle("  " + "构建🚀".repeat(20) + "  ");

    expect(Array.from(title)).toHaveLength(32);
    expect(title.endsWith("\ud83d")).toBe(false);
  });

  it("按今天、最近七天和更早稳定分组", () => {
    /** 验证任务日期分组使用固定当前时间时可以重复断言。 */
    const now = new Date("2026-09-05T12:00:00+08:00");

    expect(historyGroup(new Date("2026-09-05T08:00:00+08:00").getTime(), now)).toBe(
      "今天",
    );
    expect(historyGroup(new Date("2026-09-01T08:00:00+08:00").getTime(), now)).toBe(
      "最近 7 天",
    );
    expect(historyGroup(new Date("2026-08-01T08:00:00+08:00").getTime(), now)).toBe(
      "更早",
    );
  });
});
