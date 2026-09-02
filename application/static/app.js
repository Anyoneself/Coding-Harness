const STORAGE_KEY = "coding-harness-threads-v1";
const WORKSPACE_KEY = `${STORAGE_KEY}:workspace`;
const TERMINAL_STATUSES = new Set(["completed", "failed", "interrupted", "cancelled"]);

const state = {
  running: false,
  config: null,
  workspaceId: localStorage.getItem(WORKSPACE_KEY) || "",
  currentTurnId: "",
  eventCount: 0,
  eventSequence: 0,
  streamedAnswer: "",
  assistantNode: null,
  assistantPersisted: false,
  chats: [],
  activeChatId: "",
};

const elements = {
  composer: document.querySelector("#composer"),
  input: document.querySelector("#messageInput"),
  sendButton: document.querySelector("#sendButton"),
  sendIcon: document.querySelector("#sendIcon"),
  conversation: document.querySelector("#conversation"),
  emptyState: document.querySelector("#emptyState"),
  messageList: document.querySelector("#messageList"),
  newTask: document.querySelector("#newTaskButton"),
  taskTitle: document.querySelector("#taskTitle"),
  modelBadge: document.querySelector("#modelBadge"),
  runStatus: document.querySelector("#runStatus"),
  configBanner: document.querySelector("#configBanner"),
  sidebarStatusDot: document.querySelector("#sidebarStatusDot"),
  sidebarStatusText: document.querySelector("#sidebarStatusText"),
  activityPanel: document.querySelector("#activityPanel"),
  activityToggle: document.querySelector("#activityToggle"),
  closeActivity: document.querySelector("#closeActivity"),
  traceBackdrop: document.querySelector("#traceBackdrop"),
  activityStream: document.querySelector("#activityStream"),
  activityStatus: document.querySelector("#activityStatus"),
  eventCount: document.querySelector("#eventCount"),
  eventSequence: document.querySelector("#eventSequence"),
  chatHistory: document.querySelector("#chatHistory"),
  sidebar: document.querySelector("#sidebar"),
  sidebarToggle: document.querySelector("#sidebarToggle"),
  sidebarClose: document.querySelector("#sidebarClose"),
  sidebarScrim: document.querySelector("#sidebarScrim"),
  apiKeySetup: document.querySelector("#apiKeySetup"),
  apiKeyForm: document.querySelector("#apiKeyForm"),
  apiKeyInput: document.querySelector("#apiKeyInput"),
  apiKeyStatus: document.querySelector("#apiKeyStatus"),
  saveApiKeyButton: document.querySelector("#saveApiKeyButton"),
  toggleApiKeyVisibility: document.querySelector("#toggleApiKeyVisibility"),
};

function nowLabel() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

function createChat() {
  return {
    id: crypto.randomUUID(),
    threadId: "",
    title: "新任务",
    status: "等待输入",
    updatedAt: Date.now(),
    messages: [],
  };
}

function loadChats() {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    state.chats = Array.isArray(stored) ? stored.slice(0, 30) : [];
  } catch {
    state.chats = [];
  }
}

function persistChats() {
  state.chats = [...state.chats]
    .sort((left, right) => right.updatedAt - left.updatedAt)
    .slice(0, 30);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.chats));
}

function activeChat() {
  return state.chats.find((chat) => chat.id === state.activeChatId) || null;
}

function ensureActiveChat() {
  if (!state.chats.length) state.chats.push(createChat());
  const savedId = localStorage.getItem(`${STORAGE_KEY}:active`);
  const selected = state.chats.find((chat) => chat.id === savedId) || state.chats[0];
  state.activeChatId = selected.id;
}

function historyGroup(updatedAt) {
  const date = new Date(updatedAt);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return "今天";
  return today.getTime() - date.getTime() < 7 * 86400000 ? "最近 7 天" : "更早";
}

function renderChatHistory() {
  elements.chatHistory.replaceChildren();
  let renderedGroup = "";
  [...state.chats]
    .sort((left, right) => right.updatedAt - left.updatedAt)
    .forEach((chat) => {
      const group = historyGroup(chat.updatedAt);
      if (group !== renderedGroup) {
        const label = document.createElement("p");
        label.className = "history-group-label";
        label.textContent = group;
        elements.chatHistory.append(label);
        renderedGroup = group;
      }
      const row = document.createElement("div");
      row.className = "history-item-row";
      const button = document.createElement("button");
      button.type = "button";
      button.className = `history-item${chat.id === state.activeChatId ? " active" : ""}`;
      const title = document.createElement("strong");
      title.textContent = chat.title;
      const status = document.createElement("small");
      status.textContent = chat.status;
      button.append(title, status);
      button.addEventListener("click", () => selectChat(chat.id));
      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.className = "history-delete-button";
      removeButton.title = `从列表移除：${chat.title}`;
      removeButton.setAttribute("aria-label", removeButton.title);
      removeButton.disabled = state.running;
      removeButton.innerHTML = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 7h14M9 7V4.8h6V7m-8 0 1 12h8l1-12M10 10.5v5M14 10.5v5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      removeButton.addEventListener("click", () => removeChat(chat.id));
      row.append(button, removeButton);
      elements.chatHistory.append(row);
    });
}

function setEmptyMode(isEmpty) {
  elements.emptyState.classList.toggle("hidden", !isEmpty);
  elements.conversation.classList.toggle("is-empty", isEmpty);
  document.querySelector(".chat-main")?.classList.toggle("is-empty", isEmpty);
}

function resizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 180)}px`;
}

function setStatus(text, status = "Idle") {
  elements.runStatus.textContent = text;
  elements.activityStatus.textContent = status;
}

function setChatStatus(status) {
  const chat = activeChat();
  if (!chat) return;
  chat.status = status;
  chat.updatedAt = Date.now();
  persistChats();
  renderChatHistory();
}

function setRunning(running) {
  state.running = running;
  elements.input.disabled = running;
  elements.sendButton.classList.toggle("running", running);
  elements.sendIcon.textContent = running ? "■" : "↑";
  elements.sendButton.title = running ? "中断任务" : "发送";
  elements.sendButton.setAttribute("aria-label", running ? "中断任务" : "发送任务");
  renderChatHistory();
  if (!running) elements.input.focus();
}

function createMessageNode(role, content, pending = false) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "assistant-avatar";
    avatar.textContent = "H";
    article.append(avatar);
  }
  const body = document.createElement("div");
  body.className = "message-body";
  const heading = document.createElement("div");
  heading.className = "message-heading";
  const name = document.createElement("strong");
  name.textContent = role === "user" ? "你" : "Coding-Harness";
  const time = document.createElement("span");
  time.textContent = nowLabel();
  heading.append(name, time);
  const text = document.createElement("div");
  text.className = `message-content${pending ? " pending" : ""}`;
  if (pending) {
    const dots = document.createElement("span");
    dots.className = "thinking-dots";
    dots.innerHTML = "<span></span><span></span><span></span>";
    const label = document.createElement("span");
    label.className = "thinking-label";
    label.textContent = content;
    text.append(dots, label);
  } else {
    text.textContent = content;
  }
  const meta = document.createElement("div");
  meta.className = "message-meta";
  body.append(heading, text, meta);
  article.append(body);
  return { article, text, meta };
}

function addMessage(role, content, { pending = false, persist = true } = {}) {
  setEmptyMode(false);
  const node = createMessageNode(role, content, pending);
  elements.messageList.append(node.article);
  if (persist) {
    const chat = activeChat();
    chat.messages.push({ role, content });
    if (role === "user" && chat.title === "新任务") chat.title = content.slice(0, 28);
    chat.updatedAt = Date.now();
    persistChats();
    renderChatHistory();
    elements.taskTitle.textContent = chat.title;
  }
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
  return node;
}

function updateAssistant(content, isError = false) {
  if (!state.assistantNode) {
    state.assistantNode = addMessage("assistant", content, { persist: false });
  }
  state.assistantNode.text.classList.remove("pending");
  state.assistantNode.text.textContent = content;
  state.assistantNode.text.classList.toggle("error-text", isError);
  if (!state.assistantPersisted) {
    activeChat().messages.push({ role: "assistant", content });
    state.assistantPersisted = true;
    persistChats();
  }
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

function appendAssistantDelta(delta) {
  state.streamedAnswer += delta;
  state.assistantNode.text.classList.remove("pending");
  state.assistantNode.text.textContent = state.streamedAnswer;
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

function addMeta(label) {
  if (!state.assistantNode) return;
  const chip = document.createElement("span");
  chip.className = "meta-chip";
  chip.textContent = label;
  state.assistantNode.meta.append(chip);
}

function clearActivity() {
  state.eventCount = 0;
  state.eventSequence = 0;
  elements.eventCount.textContent = "0";
  elements.eventSequence.textContent = "0";
  elements.activityStream.replaceChildren();
}

function addActivity(kind, title, body = "", details = null) {
  const item = document.createElement("div");
  item.className = `activity-event ${kind}`;
  const dot = document.createElement("span");
  dot.className = "event-dot";
  const heading = document.createElement("div");
  heading.className = "event-heading";
  const headingText = document.createElement("strong");
  headingText.textContent = title;
  const time = document.createElement("span");
  time.textContent = nowLabel();
  heading.append(headingText, time);
  item.append(dot, heading);
  if (body) {
    const description = document.createElement("div");
    description.className = "event-body";
    description.textContent = body;
    item.append(description);
  }
  if (details) {
    const detailNode = document.createElement("pre");
    detailNode.className = "event-details";
    detailNode.textContent = JSON.stringify(details, null, 2);
    item.append(detailNode);
  }
  elements.activityStream.append(item);
  elements.activityStream.scrollTop = elements.activityStream.scrollHeight;
}

function handleTurnEvent(event) {
  state.eventCount += 1;
  state.eventSequence = Math.max(state.eventSequence, Number(event.sequence || 0));
  elements.eventCount.textContent = String(state.eventCount);
  elements.eventSequence.textContent = String(state.eventSequence);
  const item = event.payload?.item;
  if (event.type === "turn.queued") {
    setStatus("任务已排队", "Queued");
    addActivity("model", "Turn 已创建", event.turn_id);
  } else if (event.type === "turn.running") {
    setStatus("任务执行中", "Running");
    addActivity("model", "Runtime 已领取任务");
  } else if (event.type === "item.in_progress" && item?.type === "agent_message") {
    appendAssistantDelta(String(item.payload?.delta || ""));
  } else if (event.type === "item.completed" && item?.type === "agent_message") {
    const answer = String(item.payload?.answer || state.streamedAnswer);
    updateAssistant(answer);
    if (item.payload?.usage?.total_tokens) addMeta(`${item.payload.usage.total_tokens} tokens`);
    addActivity("final", "模型结果已持久化");
  } else if (event.type === "item.failed") {
    const message = String(item?.payload?.message || "任务执行失败。");
    updateAssistant(message, true);
    addActivity("error", "执行项失败", message, item?.payload);
  } else if (event.type.startsWith("turn.")) {
    const status = event.type.slice(5);
    if (TERMINAL_STATUSES.has(status)) {
      const labels = {
        completed: "任务完成",
        failed: "执行失败",
        interrupted: "任务已中断",
        cancelled: "任务已取消",
      };
      setStatus(labels[status], status);
      setChatStatus(labels[status]);
      addActivity(status === "completed" ? "final" : "error", labels[status]);
    }
  }
}

function parseEventBlock(block) {
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  return data ? JSON.parse(data) : null;
}

async function consumeEventStream(response) {
  if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    blocks.forEach((block) => {
      const event = parseEventBlock(block);
      if (event) handleTurnEvent(event);
    });
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function ensureWorkspace() {
  if (state.workspaceId) return state.workspaceId;
  const workspace = await requestJson("/api/workspaces", {
    method: "POST",
    body: JSON.stringify({
      root_path: state.config.workspace_root,
      permission_profile: "read_only",
    }),
  });
  state.workspaceId = workspace.id;
  localStorage.setItem(WORKSPACE_KEY, state.workspaceId);
  return state.workspaceId;
}

async function ensureThread(message, retry = true) {
  const chat = activeChat();
  if (chat.threadId) return chat.threadId;
  try {
    const workspaceId = await ensureWorkspace();
    const thread = await requestJson(`/api/workspaces/${workspaceId}/threads`, {
      method: "POST",
      body: JSON.stringify({ title: message.slice(0, 80) }),
    });
    chat.threadId = thread.id;
    persistChats();
    return chat.threadId;
  } catch (error) {
    if (retry && error.status === 404) {
      state.workspaceId = "";
      localStorage.removeItem(WORKSPACE_KEY);
      return ensureThread(message, false);
    }
    throw error;
  }
}

async function sendTask(message) {
  if (!state.config?.ready) {
    openApiKeySetup();
    return;
  }
  clearActivity();
  state.streamedAnswer = "";
  state.assistantPersisted = false;
  addMessage("user", message);
  state.assistantNode = addMessage("assistant", "正在创建 Turn", {
    pending: true,
    persist: false,
  });
  elements.input.value = "";
  resizeInput();
  setRunning(true);
  setChatStatus("执行中");
  try {
    const threadId = await ensureThread(message);
    const turn = await requestJson(`/api/threads/${threadId}/turns`, {
      method: "POST",
      body: JSON.stringify({ prompt: message }),
    });
    state.currentTurnId = turn.id;
    const response = await fetch(`/api/turns/${turn.id}/events/stream?after_sequence=0`);
    await consumeEventStream(response);
  } catch (error) {
    updateAssistant(`执行链连接失败：${error.message}`, true);
    setStatus("连接失败", "Error");
    setChatStatus("连接失败");
  } finally {
    state.currentTurnId = "";
    setRunning(false);
  }
}

async function interruptCurrentTurn() {
  if (!state.currentTurnId) return;
  elements.sendButton.disabled = true;
  setStatus("正在请求中断", "Interrupting");
  try {
    await requestJson(`/api/turns/${state.currentTurnId}/interrupt`, { method: "POST" });
  } catch (error) {
    setStatus(`中断失败：${error.message}`, "Error");
  } finally {
    elements.sendButton.disabled = false;
  }
}

function renderActiveChat() {
  const chat = activeChat();
  elements.messageList.replaceChildren();
  state.assistantNode = null;
  elements.taskTitle.textContent = chat?.title || "新任务";
  setStatus(chat?.status || "准备就绪");
  const messages = chat?.messages || [];
  setEmptyMode(messages.length === 0);
  messages.forEach((message) => {
    elements.messageList.append(createMessageNode(message.role, message.content).article);
  });
}

function selectChat(chatId) {
  if (state.running || chatId === state.activeChatId) return;
  state.activeChatId = chatId;
  localStorage.setItem(`${STORAGE_KEY}:active`, chatId);
  clearActivity();
  renderChatHistory();
  renderActiveChat();
  closeSidebar();
}

function removeChat(chatId) {
  if (state.running) return;
  state.chats = state.chats.filter((chat) => chat.id !== chatId);
  if (!state.chats.length) state.chats.push(createChat());
  if (state.activeChatId === chatId) state.activeChatId = state.chats[0].id;
  localStorage.setItem(`${STORAGE_KEY}:active`, state.activeChatId);
  persistChats();
  renderChatHistory();
  renderActiveChat();
}

function createNewTask() {
  if (state.running) return;
  const chat = createChat();
  state.chats.unshift(chat);
  state.activeChatId = chat.id;
  localStorage.setItem(`${STORAGE_KEY}:active`, chat.id);
  persistChats();
  clearActivity();
  renderChatHistory();
  renderActiveChat();
  closeSidebar();
  elements.input.focus();
}

function openTrace() {
  elements.activityPanel.classList.add("open");
  elements.traceBackdrop.classList.add("open");
}

function closeTrace() {
  elements.activityPanel.classList.remove("open");
  elements.traceBackdrop.classList.remove("open");
}

function openSidebar() {
  elements.sidebar.classList.add("open");
  elements.sidebarScrim.classList.add("open");
}

function closeSidebar() {
  elements.sidebar.classList.remove("open");
  elements.sidebarScrim.classList.remove("open");
}

function openApiKeySetup() {
  elements.apiKeySetup.classList.remove("hidden");
  setTimeout(() => elements.apiKeyInput.focus(), 0);
}

function closeApiKeySetup() {
  elements.apiKeyInput.value = "";
  elements.apiKeyInput.type = "password";
  elements.apiKeyStatus.textContent = "";
  elements.apiKeySetup.classList.add("hidden");
}

async function configureApiKey() {
  const apiKey = elements.apiKeyInput.value.trim();
  if (!apiKey) return;
  elements.saveApiKeyButton.disabled = true;
  elements.saveApiKeyButton.textContent = "正在连接";
  elements.apiKeyStatus.textContent = "";
  try {
    await requestJson("/api/config/api-key", {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    });
    await loadConfig();
  } catch (error) {
    elements.apiKeyStatus.textContent =
      error.status === 409 ? "API Key 已完成配置，请刷新页面。" : "API Key 无效，请检查后重试。";
  } finally {
    elements.saveApiKeyButton.disabled = false;
    elements.saveApiKeyButton.textContent = "保存并连接";
  }
}

function toggleApiKeyVisibility() {
  const show = elements.apiKeyInput.type === "password";
  elements.apiKeyInput.type = show ? "text" : "password";
  const label = show ? "隐藏 API Key" : "显示 API Key";
  elements.toggleApiKeyVisibility.setAttribute("aria-label", label);
  elements.toggleApiKeyVisibility.title = label;
}

async function loadConfig() {
  try {
    state.config = await requestJson("/api/config");
    elements.modelBadge.textContent = state.config.model;
    elements.sidebarStatusDot.className = `status-dot ${state.config.ready ? "ready" : "error"}`;
    elements.sidebarStatusText.textContent = state.config.ready ? "Harness 已就绪" : "等待 API Key";
    if (state.config.ready) closeApiKeySetup();
    else openApiKeySetup();
  } catch (error) {
    elements.configBanner.textContent = `无法读取服务配置：${error.message}`;
    elements.configBanner.classList.remove("hidden");
  }
}

function initialize() {
  loadChats();
  ensureActiveChat();
  renderChatHistory();
  renderActiveChat();
  loadConfig();
}

elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.running) {
    interruptCurrentTurn();
    return;
  }
  const message = elements.input.value.trim();
  if (message) sendTask(message);
});
elements.input.addEventListener("input", resizeInput);
elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    elements.composer.requestSubmit();
  }
});
elements.newTask.addEventListener("click", createNewTask);
elements.activityToggle.addEventListener("click", openTrace);
elements.closeActivity.addEventListener("click", closeTrace);
elements.traceBackdrop.addEventListener("click", closeTrace);
elements.sidebarToggle.addEventListener("click", openSidebar);
elements.sidebarClose.addEventListener("click", closeSidebar);
elements.sidebarScrim.addEventListener("click", closeSidebar);
elements.apiKeyForm.addEventListener("submit", (event) => {
  event.preventDefault();
  configureApiKey();
});
elements.toggleApiKeyVisibility.addEventListener("click", toggleApiKeyVisibility);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeTrace();
    closeSidebar();
  }
});

initialize();
