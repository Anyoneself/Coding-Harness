import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

interface MockResponse {
  ok: boolean;
  status?: number;
  json?: () => Promise<unknown>;
  body?: {
    getReader: () => {
      read: () => Promise<ReadableStreamReadResult<Uint8Array>>;
    };
  };
}

/** 创建不依赖浏览器 Response 实现的 JSON Fetch 响应。 */
function jsonResponse(value: unknown, status = 200): MockResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => value,
  };
}

/** 创建按指定文本块结束的可控 SSE Fetch 响应。 */
function streamResponse(chunks: string[]): MockResponse {
  const values = chunks.map((chunk) => new TextEncoder().encode(chunk));
  let index = 0;
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () => {
          const value = values[index];
          index += 1;
          return value
            ? { done: false, value }
            : { done: true, value: undefined };
        },
      }),
    },
  };
}

/** 安装覆盖完整任务创建链路的同源 Fetch Mock。 */
function installExecutionFetch(events: string[]): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/config") {
      return jsonResponse({
        ready: true,
        model: "deepseek-v4-flash",
        workspace_root: "/workspace/Coding-Harness",
      });
    }
    if (url === "/api/workspaces") {
      return jsonResponse({ id: "workspace-1" });
    }
    if (url === "/api/workspaces/workspace-1/threads") {
      return jsonResponse({ id: "thread-1" });
    }
    if (url === "/api/threads/thread-1/turns") {
      return jsonResponse({ id: "turn-1" });
    }
    if (url.startsWith("/api/turns/turn-1/events/stream")) {
      return streamResponse(events);
    }
    if (url === "/api/turns/turn-1/interrupt") {
      return jsonResponse({ id: "turn-1" });
    }
    throw new Error(`未处理的测试请求：${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("Coding-Harness 工作台", () => {
  beforeEach(() => {
    /** 为每个工作台行为测试提供独立的本地历史和公开配置。 */
    localStorage.clear();
    vi.restoreAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ready: true,
          model: "deepseek-v4-flash",
          workspace_root: "/workspace/Coding-Harness",
        }),
      }),
    );
  });

  it("呈现工作台核心入口和可访问的任务输入", async () => {
    /** 验证执行工作台的主要控制在初始状态即可访问。 */
    render(<App />);

    expect(screen.getByRole("button", { name: "新建任务" })).toBeVisible();
    expect(screen.getByRole("textbox", { name: "任务输入" })).toBeVisible();
    expect(
      screen.getByRole("tab", { name: "事件", hidden: true }),
    ).toBeInTheDocument();
    expect(await screen.findByTitle("当前模型")).toHaveTextContent(
      "deepseek-v4-flash",
    );
  });

  it("呈现参考图映射后的品牌空状态和真实导航", async () => {
    /** 验证空状态只展示当前产品实际支持的执行视图。 */
    render(<App />);

    expect(
      screen.getByRole("heading", {
        name: "你想让我们在 Coding-Harness 中构建什么？",
      }),
    ).toBeVisible();
    expect(screen.getByRole("navigation", { name: "主导航" })).toBeVisible();
    expect(screen.getByRole("button", { name: "工作台" })).toBeVisible();
    expect(screen.getByRole("button", { name: "执行事件" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Turn" })).toBeVisible();
    expect(await screen.findByRole("region", { name: "当前项目" })).toHaveTextContent(
      "Coding-Harness",
    );
    expect(screen.queryByRole("button", { name: "评估" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "工具" })).not.toBeInTheDocument();
  });

  it("通过顶部导航选择现有检查器标签", async () => {
    /** 验证顶部导航复用 Event 和 Turn 检查器，不创造新业务视图。 */
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Turn" }));
    expect(screen.getByRole("tab", { name: "Turn" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await user.click(screen.getByRole("button", { name: "执行事件" }));
    expect(screen.getByRole("tab", { name: "事件" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    const inspector = screen.getByRole("complementary", {
      name: "Turn 检查器",
    });
    await user.click(screen.getByRole("button", { name: "工作台" }));
    expect(inspector).not.toHaveClass("is-open");
    expect(inspector).toHaveAttribute("aria-hidden", "true");
  });

  it("为移动抽屉保留独立且可访问的控制", () => {
    /** 验证响应式样式隐藏控件前，DOM 已提供稳定可访问名称。 */
    render(<App />);

    expect(
      screen.getByRole("button", { name: "打开任务导航" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "打开执行检查器" }),
    ).toBeInTheDocument();
  });

  it("把执行检查器作为默认隐藏且可关闭的按需抽屉", async () => {
    /** 验证检查器不再作为桌面永久栏，并保持明确的可访问状态。 */
    const user = userEvent.setup();
    render(<App />);

    const hiddenInspector = document.querySelector<HTMLElement>(".inspector");
    expect(hiddenInspector).not.toBeNull();
    if (!hiddenInspector) {
      throw new Error("执行检查器未渲染");
    }
    expect(hiddenInspector).toHaveAttribute("aria-hidden", "true");

    await user.click(screen.getByRole("button", { name: "执行事件" }));
    expect(hiddenInspector).toHaveAttribute("aria-hidden", "false");

    await user.click(
      within(hiddenInspector).getByRole("button", { name: "关闭执行检查器" }),
    );
    expect(hiddenInspector).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("button", { name: "工作台" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("保留 Enter 发送与 Shift+Enter 换行契约", async () => {
    /** 验证键盘提交只创建一个 Turn，并保留任务中的显式换行。 */
    const user = userEvent.setup();
    const fetchMock = installExecutionFetch([
      'data: {"type":"turn.running","sequence":1,"turn_id":"turn-1","payload":{}}\n\n',
      'data: {"type":"item.completed","sequence":2,"turn_id":"turn-1","payload":{"item":{"type":"agent_message","payload":{"answer":"完成"}}}}\n\n',
      'data: {"type":"turn.completed","sequence":3,"turn_id":"turn-1","payload":{}}\n\n',
    ]);
    render(<App />);

    const input = screen.getByRole("textbox", { name: "任务输入" });
    await user.type(input, "第一行{shift>}{enter}{/shift}第二行");
    expect(input).toHaveValue("第一行\n第二行");
    await user.type(input, "{enter}");

    expect(await screen.findByText("完成")).toBeVisible();
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).includes("/threads/thread-1/turns"),
      ),
    ).toHaveLength(1);
  });

  it("在模型未配置时通过现有对话框收集密钥", async () => {
    /** 验证未配置状态不会伪装成已发送任务。 */
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          ready: false,
          model: "deepseek-v4-flash",
          workspace_root: "/workspace/Coding-Harness",
        }),
      ),
    );
    render(<App />);

    expect(await screen.findByRole("dialog", { name: "连接 DeepSeek" })).toBeVisible();
    expect(JSON.stringify(localStorage)).not.toContain("sk-");
    await user.type(screen.getByLabelText("API Key"), "sk-abcdefghijklmnop");
    expect(screen.getByLabelText("API Key")).toHaveValue("sk-abcdefghijklmnop");
  });

  it("配置读取失败时禁用发送且不打开密钥对话框", async () => {
    /** 验证未知配置状态使用连接失败路径，而不是误判为首次配置。 */
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);

    expect(
      await screen.findByRole("alert", {
        name: "",
      }),
    ).toHaveTextContent("无法读取 Harness 配置");
    const input = screen.getByRole("textbox", { name: "任务输入" });
    await user.type(input, "不会发送");
    expect(screen.getByRole("button", { name: "发送任务" })).toBeDisabled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("非终态 SSE 结束时进入连接失败且不持久化部分回答", async () => {
    /** 验证异常 EOF 不会把部分回答写成成功的 Assistant 历史。 */
    const user = userEvent.setup();
    installExecutionFetch([
      'data: {"type":"turn.running","sequence":1,"turn_id":"turn-1","payload":{}}\n\n',
      'data: {"type":"item.in_progress","sequence":2,"turn_id":"turn-1","payload":{"item":{"type":"agent_message","payload":{"delta":"部分回答"}}}}\n\n',
    ]);
    render(<App />);

    await user.type(screen.getByRole("textbox", { name: "任务输入" }), "执行任务");
    await user.click(screen.getByRole("button", { name: "发送任务" }));

    expect(await screen.findByText(/事件连接已提前结束/)).toBeVisible();
    await waitFor(() => {
      expect(localStorage.getItem("coding-harness-threads-v1")).not.toContain(
        "部分回答",
      );
    });
  });

  it("活动任务使用语义状态并在运行时锁定管理操作", async () => {
    /** 验证执行期间任务管理禁用原因可感知，当前任务仍可中断。 */
    const user = userEvent.setup();
    let finishStream: (() => void) | undefined;
    const streamFinished = new Promise<void>((resolve) => {
      finishStream = resolve;
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/config") {
        return jsonResponse({
          ready: true,
          model: "deepseek-v4-flash",
          workspace_root: "/workspace/Coding-Harness",
        });
      }
      if (url === "/api/workspaces") {
        return jsonResponse({ id: "workspace-1" });
      }
      if (url.includes("/threads") && !url.includes("/turns")) {
        return jsonResponse({ id: "thread-1" });
      }
      if (url.includes("/turns") && !url.includes("events")) {
        return jsonResponse({ id: "turn-1" });
      }
      if (url.includes("events/stream")) {
        let readCount = 0;
        return {
          ok: true,
          status: 200,
          body: {
            getReader: () => ({
              read: async () => {
                readCount += 1;
                if (readCount === 1) {
                  return {
                    done: false,
                    value: new TextEncoder().encode(
                      'data: {"type":"turn.running","sequence":1,"turn_id":"turn-1","payload":{}}\n\n',
                    ),
                  };
                }
                await streamFinished;
                return { done: true, value: undefined };
              },
            }),
          },
        };
      }
      throw new Error(`未处理的测试请求：${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await user.type(screen.getByRole("textbox", { name: "任务输入" }), "持续执行");
    await user.click(screen.getByRole("button", { name: "发送任务" }));
    expect(await screen.findByRole("button", { name: "中断任务" })).toBeVisible();
    expect(screen.getByRole("button", { name: "新建任务" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "新建任务" })).toHaveAccessibleDescription(
      "当前 Turn 运行期间不可新建、切换或移除任务",
    );
    const threadList = screen.getByRole("navigation", { name: "最近任务" });
    const activeThread = within(threadList)
      .getAllByRole("button")
      .find((button) => button.classList.contains("thread-button"));
    expect(activeThread).toHaveAttribute("aria-current", "true");
    finishStream?.();
  });

  it("移动抽屉互斥并在关闭后恢复触发控件焦点", async () => {
    /** 验证两侧抽屉不会同时打开，关闭后键盘流程返回原入口。 */
    const user = userEvent.setup();
    render(<App />);

    const sidebar = screen.getByRole("complementary", { name: "任务导航" });
    const inspector = document.querySelector<HTMLElement>(".inspector");
    expect(inspector).not.toBeNull();
    if (!inspector) {
      throw new Error("执行检查器未渲染");
    }
    const openSidebar = screen.getByRole("button", { name: "打开任务导航" });
    await user.click(openSidebar);
    expect(sidebar).toHaveAttribute("aria-hidden", "false");

    const openInspector = screen.getByRole("button", { name: "打开执行检查器" });
    await user.click(openInspector);
    expect(sidebar).not.toHaveClass("is-open");
    expect(inspector).toHaveAttribute("aria-hidden", "false");

    await user.click(
      within(inspector).getByRole("button", { name: "关闭执行检查器" }),
    );
    expect(openInspector).toHaveFocus();
  });

  it("打开和关闭检查器后保留未发送草稿", async () => {
    /** 验证覆盖式检查器不重建 Composer 或丢失本地输入。 */
    const user = userEvent.setup();
    render(<App />);

    const input = screen.getByRole("textbox", { name: "任务输入" });
    await user.type(input, "尚未发送的草稿");
    await user.click(screen.getByRole("button", { name: "执行事件" }));
    await user.click(screen.getByRole("button", { name: "Turn" }));
    const inspector = document.querySelector<HTMLElement>(".inspector");
    expect(inspector).not.toBeNull();
    if (!inspector) {
      throw new Error("执行检查器未渲染");
    }
    await user.click(
      within(inspector).getByRole("button", { name: "关闭执行检查器" }),
    );

    expect(input).toHaveValue("尚未发送的草稿");
    expect(screen.getByRole("button", { name: "工作台" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
