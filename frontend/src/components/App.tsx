import { useEffect, useMemo, useRef, useState } from "react";

import {
  configureApiKey,
  createThread,
  createTurn,
  createWorkspace,
  getPublicConfig,
  HttpError,
  interruptTurn,
  streamTurnEvents,
} from "../api/harness";
import {
  ACTIVE_CHAT_KEY,
  CHAT_STORAGE_KEY,
  createChat,
  createMessage,
  loadStoredChats,
  normalizeChatTitle,
  sortAndLimitChats,
  WORKSPACE_STORAGE_KEY,
} from "../domain/chat";
import {
  createExecutionState,
  isTerminalStatus,
  reduceTurnEvent,
} from "../domain/events";
import type {
  ChatThread,
  ExecutionState,
  PublicConfig,
  TurnEvent,
  WorkbenchView,
} from "../domain/types";
import { ApiKeyDialog } from "./ApiKeyDialog";
import { Composer } from "./Composer";
import { Inspector, type InspectorTab } from "./Inspector";
import { MessageList } from "./MessageList";
import { Sidebar } from "./Sidebar";
import { TopNavigation } from "./TopNavigation";

/** 装配客户端状态、API 生命周期和带按需检查器的执行工作台。 */
export function App() {
  const initialChats = useMemo(() => {
    const stored = loadStoredChats(localStorage.getItem(CHAT_STORAGE_KEY));
    return stored.length ? stored : [createChat()];
  }, []);
  const [chats, setChats] = useState<ChatThread[]>(initialChats);
  const [activeChatId, setActiveChatId] = useState(() => {
    const saved = localStorage.getItem(ACTIVE_CHAT_KEY);
    return initialChats.some((chat) => chat.id === saved)
      ? (saved as string)
      : initialChats[0].id;
  });
  const [workspaceId, setWorkspaceId] = useState(
    () => localStorage.getItem(WORKSPACE_STORAGE_KEY) ?? "",
  );
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [configError, setConfigError] = useState("");
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [isConfigSubmitting, setIsConfigSubmitting] = useState(false);
  const [execution, setExecution] = useState<ExecutionState>(
    createExecutionState,
  );
  const [isRunning, setIsRunning] = useState(false);
  const [showLiveAssistant, setShowLiveAssistant] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const [activeView, setActiveView] = useState<WorkbenchView>("workspace");
  const sidebarTriggerRef = useRef<HTMLButtonElement>(null);
  const inspectorTriggerRef = useRef<HTMLButtonElement>(null);

  const activeChat =
    chats.find((chat) => chat.id === activeChatId) ?? chats[0];
  const projectName = workspaceName(config?.workspace_root);
  const hasConversation =
    activeChat.messages.length > 0 || showLiveAssistant;

  useEffect(() => {
    localStorage.setItem(
      CHAT_STORAGE_KEY,
      JSON.stringify(sortAndLimitChats(chats)),
    );
  }, [chats]);

  useEffect(() => {
    localStorage.setItem(ACTIVE_CHAT_KEY, activeChatId);
  }, [activeChatId]);

  useEffect(() => {
    /** 初始化公开配置，并在未配置时打开本机密钥对话框。 */
    async function loadConfig(): Promise<void> {
      try {
        const nextConfig = await getPublicConfig();
        setConfig(nextConfig);
        setIsConfigOpen(!nextConfig.ready);
      } catch {
        setConfigError("无法读取 Harness 配置，请确认服务仍在运行。");
      }
    }
    void loadConfig();
  }, []);

  /** 原子更新当前本地 Thread，避免组件复制持久化规则。 */
  function updateActiveChat(
    transform: (chat: ChatThread) => ChatThread,
  ): void {
    setChats((current) =>
      current.map((chat) => (chat.id === activeChatId ? transform(chat) : chat)),
    );
  }

  /** 创建新的本地任务并清空当前检查器状态。 */
  function handleCreateChat(): void {
    if (isRunning) {
      return;
    }
    const chat = createChat();
    setChats((current) => [chat, ...current]);
    setActiveChatId(chat.id);
    setExecution(createExecutionState());
    setShowLiveAssistant(false);
    setIsSidebarOpen(false);
  }

  /** 切换本地任务，不在运行中切走正在执行的 Turn。 */
  function handleSelectChat(chatId: string): void {
    if (isRunning || chatId === activeChatId) {
      return;
    }
    setActiveChatId(chatId);
    setExecution(createExecutionState());
    setShowLiveAssistant(false);
    setIsSidebarOpen(false);
  }

  /** 从浏览器历史移除任务，至少保留一个可输入的空任务。 */
  function handleRemoveChat(chatId: string): void {
    if (isRunning) {
      return;
    }
    const remaining = chats.filter((chat) => chat.id !== chatId);
    const nextChats = remaining.length ? remaining : [createChat()];
    setChats(nextChats);
    if (chatId === activeChatId) {
      setActiveChatId(nextChats[0].id);
      setExecution(createExecutionState());
      setShowLiveAssistant(false);
    }
  }

  /** 确保浏览器持有有效 Workspace，过期 ID 仅重试一次。 */
  async function ensureWorkspace(retry = true): Promise<string> {
    if (workspaceId) {
      return workspaceId;
    }
    try {
      const workspace = await createWorkspace(config?.workspace_root ?? ".");
      setWorkspaceId(workspace.id);
      localStorage.setItem(WORKSPACE_STORAGE_KEY, workspace.id);
      return workspace.id;
    } catch (error) {
      if (retry && error instanceof HttpError && error.status === 404) {
        setWorkspaceId("");
        localStorage.removeItem(WORKSPACE_STORAGE_KEY);
        return ensureWorkspace(false);
      }
      throw error;
    }
  }

  /** 确保当前本地任务已绑定服务端 Thread。 */
  async function ensureThread(
    message: string,
    retry = true,
  ): Promise<string> {
    if (activeChat.threadId) {
      return activeChat.threadId;
    }
    try {
      const currentWorkspaceId = await ensureWorkspace();
      const thread = await createThread(currentWorkspaceId, message);
      updateActiveChat((chat) => ({ ...chat, threadId: thread.id }));
      return thread.id;
    } catch (error) {
      if (retry && error instanceof HttpError && error.status === 404) {
        setWorkspaceId("");
        localStorage.removeItem(WORKSPACE_STORAGE_KEY);
        const workspace = await createWorkspace(config?.workspace_root ?? ".");
        setWorkspaceId(workspace.id);
        localStorage.setItem(WORKSPACE_STORAGE_KEY, workspace.id);
        const thread = await createThread(workspace.id, message);
        updateActiveChat((chat) => ({ ...chat, threadId: thread.id }));
        return thread.id;
      }
      throw error;
    }
  }

  /** 创建 Turn、消费公开事件，并在连接结束后持久化最终公开消息。 */
  async function handleSend(message: string): Promise<void> {
    const userMessage = createMessage("user", message);
    updateActiveChat((chat) => ({
      ...chat,
      title: chat.title === "新任务" ? normalizeChatTitle(message) : chat.title,
      status: "正在创建",
      updatedAt: Date.now(),
      messages: [...chat.messages, userMessage],
    }));
    setIsRunning(true);
    setShowLiveAssistant(true);
    let accumulated = createExecutionState();
    setExecution(accumulated);

    try {
      const threadId = await ensureThread(message);
      const turn = await createTurn(threadId, message);
      accumulated = { ...accumulated, turnId: turn.id, status: "queued" };
      setExecution(accumulated);

      /** 将单个事件同步归约到闭包快照和 React 视图。 */
      function handleEvent(event: TurnEvent): void {
        accumulated = reduceTurnEvent(accumulated, event);
        setExecution(accumulated);
        updateActiveChat((chat) => ({
          ...chat,
          status: accumulated.statusLabel,
          updatedAt: Date.now(),
        }));
      }

      await streamTurnEvents(turn.id, handleEvent);
      if (!isTerminalStatus(accumulated.status)) {
        throw new IncompleteEventStreamError();
      }
      const finalContent =
        accumulated.error ||
        accumulated.answer ||
        terminalFallback(accumulated.status);
      if (finalContent) {
        const assistantMessage = createMessage(
          "assistant",
          finalContent,
          Boolean(accumulated.error),
        );
        updateActiveChat((chat) => ({
          ...chat,
          status: accumulated.statusLabel,
          updatedAt: Date.now(),
          messages: [...chat.messages, assistantMessage],
        }));
      }
    } catch (error) {
      const messageText = errorMessage(error);
      accumulated = {
        ...accumulated,
        status: "failed",
        statusLabel: "连接失败",
        error: messageText,
      };
      setExecution(accumulated);
      const assistantMessage = createMessage("assistant", messageText, true);
      updateActiveChat((chat) => ({
        ...chat,
        status: "连接失败",
        updatedAt: Date.now(),
        messages: [...chat.messages, assistantMessage],
      }));
    } finally {
      setIsRunning(false);
      setShowLiveAssistant(false);
    }
  }

  /** 请求中断当前 Turn，并等待事件流给出最终状态。 */
  async function handleInterrupt(): Promise<void> {
    if (!execution.turnId) {
      return;
    }
    try {
      await interruptTurn(execution.turnId);
    } catch {
      setExecution((current) => ({
        ...current,
        error: "中断请求失败，请检查服务连接。",
      }));
    }
  }

  /** 安全提交首次密钥配置并重新读取公开配置。 */
  async function handleConfigureApiKey(apiKey: string): Promise<void> {
    setIsConfigSubmitting(true);
    setConfigError("");
    try {
      await configureApiKey(apiKey);
      const nextConfig = await getPublicConfig();
      setConfig(nextConfig);
      setIsConfigOpen(!nextConfig.ready);
    } catch (error) {
      setConfigError(
        error instanceof HttpError && error.status === 409
          ? "API Key 已完成配置，请刷新页面。"
          : "连接失败，请检查 API Key 后重试。",
      );
    } finally {
      setIsConfigSubmitting(false);
    }
  }

  /** 选择工作台真实视图，并在需要时打开响应式检查器。 */
  function handleSelectView(view: WorkbenchView): void {
    setActiveView(view);
    if (view === "workspace") {
      setIsInspectorOpen(false);
      return;
    }
    setIsSidebarOpen(false);
    setIsInspectorOpen(true);
  }

  /** 同步检查器内部标签与产品顶栏的瞬时视图状态。 */
  function handleInspectorTabChange(tab: InspectorTab): void {
    setActiveView(tab);
  }

  /** 打开移动任务导航，并关闭可能遮挡它的执行检查器。 */
  function handleOpenSidebar(): void {
    setIsInspectorOpen(false);
    setActiveView("workspace");
    setIsSidebarOpen(true);
  }

  /** 关闭移动任务导航并把键盘焦点归还给触发控件。 */
  function handleCloseSidebar(): void {
    setIsSidebarOpen(false);
    queueMicrotask(() => sidebarTriggerRef.current?.focus());
  }

  /** 打开事件检查器，并确保移动任务导航不会同时占据画布。 */
  function handleOpenInspector(): void {
    setIsSidebarOpen(false);
    setActiveView((current) => (current === "workspace" ? "events" : current));
    setIsInspectorOpen(true);
  }

  /** 关闭检查器、恢复工作台活动态并归还触发控件焦点。 */
  function handleCloseInspector(): void {
    setIsInspectorOpen(false);
    setActiveView("workspace");
    queueMicrotask(() => inspectorTriggerRef.current?.focus());
  }

  return (
    <div className={`app-shell${hasConversation ? " has-conversation" : ""}`}>
      <Sidebar
        chats={sortAndLimitChats(chats)}
        activeChatId={activeChatId}
        config={config}
        projectName={projectName}
        isOpen={isSidebarOpen}
        isRunning={isRunning}
        onClose={handleCloseSidebar}
        onCreate={handleCreateChat}
        onSelect={handleSelectChat}
        onRemove={handleRemoveChat}
      />

      <TopNavigation
        activeView={activeView}
        canClearInspector={isTerminalStatus(execution.status)}
        onSelectView={handleSelectView}
        onOpenSidebar={handleOpenSidebar}
        onOpenInspector={handleOpenInspector}
        onClearInspector={() => setExecution(createExecutionState())}
        sidebarTriggerRef={sidebarTriggerRef}
        inspectorTriggerRef={inspectorTriggerRef}
      />

      <main className="workspace">
        {configError && config?.ready !== false ? (
          <div className="connection-banner" role="alert">
            {configError}
          </div>
        ) : null}

        <section className="conversation" aria-label="任务对话">
          <MessageList
            messages={activeChat.messages}
            execution={execution}
            showLiveAssistant={showLiveAssistant}
            projectName={projectName}
          />
        </section>

        <Composer
          isRunning={isRunning}
          isReady={Boolean(config?.ready)}
          isUnavailable={Boolean(configError && !config)}
          model={
            config?.model ??
            (configError ? "配置读取失败" : "读取配置中")
          }
          projectName={projectName}
          onSubmit={(message) => void handleSend(message)}
          onInterrupt={() => void handleInterrupt()}
          onNeedsConfiguration={() => setIsConfigOpen(true)}
        />
      </main>

      <Inspector
        execution={execution}
        isOpen={isInspectorOpen}
        activeTab={activeView === "turn" ? "turn" : "events"}
        onClose={handleCloseInspector}
        onTabChange={handleInspectorTabChange}
      />

      <ApiKeyDialog
        isOpen={isConfigOpen}
        error={configError}
        isSubmitting={isConfigSubmitting}
        onSubmit={(apiKey) => void handleConfigureApiKey(apiKey)}
      />
    </div>
  );
}

/** 为没有公开回答的终态提供准确且简短的可见结果。 */
function terminalFallback(status: ExecutionState["status"]): string {
  const messages: Partial<Record<ExecutionState["status"], string>> = {
    interrupted: "任务已按请求中断。",
    cancelled: "任务已取消。",
    failed: "任务执行失败。",
  };
  return messages[status] ?? "";
}

/** 把未知异常转换为不泄漏响应正文的用户提示。 */
function errorMessage(error: unknown): string {
  if (error instanceof IncompleteEventStreamError) {
    return "事件连接已提前结束，请检查服务连接后重试。";
  }
  if (error instanceof HttpError) {
    return `执行链连接失败：HTTP ${error.status}`;
  }
  return "执行链连接失败，请确认服务仍在运行。";
}

/** 标记事件流未提供终态便结束的公开连接故障。 */
class IncompleteEventStreamError extends Error {}

/** 从公开 Workspace 路径派生仅用于界面展示的项目名称。 */
function workspaceName(rootPath: string | undefined): string {
  const normalized = rootPath?.replace(/\/+$/, "");
  if (!normalized || normalized === ".") {
    return "Coding-Harness";
  }
  return normalized.split("/").filter(Boolean).at(-1) ?? "Coding-Harness";
}
