const state = {
  sessionId: crypto.randomUUID(),
  running: false,
  controller: null,
  config: null,
  toolCalls: 0,
  rounds: 0,
  assistantNode: null,
  activityByCall: new Map(),
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
  taskSubtitle: document.querySelector("#taskSubtitle"),
  roleSelect: document.querySelector("#roleSelect"),
  modelSelect: document.querySelector("#modelSelect"),
  runStatus: document.querySelector("#runStatus"),
  configBanner: document.querySelector("#configBanner"),
  sidebarStatusDot: document.querySelector("#sidebarStatusDot"),
  sidebarStatusText: document.querySelector("#sidebarStatusText"),
  toolList: document.querySelector("#toolList"),
  thinkingMode: document.querySelector("#thinkingMode"),
  activityPanel: document.querySelector("#activityPanel"),
  activityToggle: document.querySelector("#activityToggle"),
  closeActivity: document.querySelector("#closeActivity"),
  activityStream: document.querySelector("#activityStream"),
  activityStatus: document.querySelector("#activityStatus"),
  toolCount: document.querySelector("#toolCount"),
  roundCount: document.querySelector("#roundCount"),
};

function nowLabel() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

function prettyJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function resizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 180)}px`;
}

function setRunning(running) {
  state.running = running;
  elements.input.disabled = running;
  elements.sendButton.classList.toggle("running", running);
  elements.sendIcon.textContent = running ? "■" : "↑";
  elements.sendButton.title = running ? "停止" : "发送";
  elements.sendButton.setAttribute("aria-label", running ? "停止任务" : "发送任务");
  if (!running) {
    elements.input.disabled = false;
    elements.input.focus();
  }
}

function setStatus(text, status = "idle") {
  elements.runStatus.textContent = text;
  elements.activityStatus.textContent = status;
}

function showConversation() {
  elements.emptyState.classList.add("hidden");
}

function addMessage(role, content, pending = false) {
  showConversation();
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = role === "user" ? "YOU" : "DS";

  const body = document.createElement("div");
  body.className = "message-body";
  const heading = document.createElement("div");
  heading.className = "message-heading";
  const name = document.createElement("strong");
  name.textContent = role === "user" ? "你" : "DeepSeek Agent";
  const time = document.createElement("span");
  time.textContent = nowLabel();
  heading.append(name, time);

  const text = document.createElement("div");
  text.className = `message-content${pending ? " pending" : ""}`;
  if (pending) {
    const bars = document.createElement("span");
    bars.className = "thinking-bars";
    bars.innerHTML = "<span></span><span></span><span></span>";
    const label = document.createElement("span");
    label.textContent = content;
    text.append(bars, label);
  } else {
    text.textContent = content;
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";
  body.append(heading, text, meta);
  article.append(avatar, body);
  elements.messageList.append(article);
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
  return { article, text, meta };
}

function updateAssistant(content, isError = false) {
  if (!state.assistantNode) {
    state.assistantNode = addMessage("assistant", content);
    return;
  }
  state.assistantNode.text.classList.remove("pending");
  state.assistantNode.text.replaceChildren();
  state.assistantNode.text.textContent = content;
  if (isError) {
    state.assistantNode.text.style.color = "var(--danger)";
  }
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
  state.toolCalls = 0;
  state.rounds = 0;
  state.activityByCall.clear();
  elements.toolCount.textContent = "0";
  elements.roundCount.textContent = "0";
  elements.activityStream.replaceChildren();
}

function addActivity(kind, title, body = "", tags = [], details = null) {
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
  if (tags.length) {
    const tagWrap = document.createElement("div");
    tagWrap.className = "event-tags";
    tags.forEach((tag) => {
      const tagNode = document.createElement("span");
      tagNode.className = "event-tag";
      tagNode.textContent = tag;
      tagWrap.append(tagNode);
    });
    item.append(tagWrap);
  }
  if (details !== null) {
    const detailNode = document.createElement("pre");
    detailNode.className = "event-details";
    detailNode.textContent = prettyJson(details);
    item.append(detailNode);
  }
  elements.activityStream.append(item);
  elements.activityStream.scrollTop = elements.activityStream.scrollHeight;
  return item;
}

function handleAgentEvent(event) {
  switch (event.type) {
    case "started":
      setStatus(`请求 ${event.request_id.slice(0, 8)} · ${event.model}`, "Running");
      addActivity("model", "任务已进入 Agent", event.model, ["request"]);
      break;
    case "intent": {
      const confidence = Math.round((event.confidence || 0) * 100);
      const tags = [...(event.intents || []), `confidence:${confidence}%`];
      addActivity(
        "intent",
        "意图识别完成",
        event.needs_clarification
          ? event.clarification_question || "模型建议澄清"
          : "已提取目标、实体和候选工具",
        tags,
        {
          entities: event.entities || {},
          suggested_tools: event.suggested_tools || [],
        },
      );
      addMeta(`intent ${confidence}%`);
      break;
    }
    case "model_round":
      state.rounds = Math.max(state.rounds, event.round || 0);
      elements.roundCount.textContent = String(state.rounds);
      setStatus(event.message || "DeepSeek 正在处理", "Running");
      addActivity("model", `模型轮次 ${event.round}`, event.message || "规划下一步");
      break;
    case "tool_call": {
      state.toolCalls += 1;
      elements.toolCount.textContent = String(state.toolCalls);
      setStatus(`正在调用 ${event.name}`, "Tool");
      const node = addActivity(
        "tool",
        event.name,
        "工具参数已通过服务端注册表",
        ["running"],
        event.arguments,
      );
      state.activityByCall.set(event.id, node);
      break;
    }
    case "tool_result": {
      const status = event.result?.status || "completed";
      addActivity(
        status === "failed" || status === "blocked" ? "error" : "tool",
        `${event.name} 返回`,
        status === "blocked" ? "执行器阻止了本次操作" : `状态：${status}`,
        [status],
        event.result,
      );
      addMeta(`${event.name}:${status}`);
      break;
    }
    case "final": {
      updateAssistant(event.answer);
      const totalTokens = event.usage?.total_tokens;
      if (totalTokens) addMeta(`${totalTokens} tokens`);
      addMeta(`${state.rounds} rounds`);
      addActivity(
        "final",
        "结果已返回",
        event.finish_reason ? `finish: ${event.finish_reason}` : "模型完成任务",
        totalTokens ? [`tokens:${totalTokens}`] : [],
      );
      setStatus("任务完成", "Done");
      elements.taskSubtitle.textContent = "已完成";
      break;
    }
    case "error":
      updateAssistant(event.message || "任务执行失败。", true);
      addActivity("error", "任务失败", event.message || "未知错误");
      setStatus("执行失败", "Error");
      elements.taskSubtitle.textContent = "失败";
      break;
    default:
      break;
  }
}

function parseEventBlock(block) {
  let eventName = "message";
  const dataLines = [];
  block.split("\n").forEach((line) => {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  });
  if (!dataLines.length) return null;
  try {
    const parsed = JSON.parse(dataLines.join("\n"));
    parsed.type ||= eventName;
    return parsed;
  } catch {
    return { type: "error", message: "无法解析服务端事件。" };
  }
}

async function consumeEventStream(response) {
  if (!response.ok || !response.body) {
    throw new Error(`HTTP ${response.status}`);
  }
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
      if (event) handleAgentEvent(event);
    });
  }
  if (buffer.trim()) {
    const event = parseEventBlock(buffer);
    if (event) handleAgentEvent(event);
  }
}

async function sendTask(message) {
  if (!state.config?.ready) {
    updateAssistant("尚未配置 DEEPSEEK_API_KEY，请先完成服务端配置。", true);
    return;
  }
  clearActivity();
  state.assistantNode = null;
  addMessage("user", message);
  state.assistantNode = addMessage("assistant", "正在识别意图并规划任务", true);
  elements.taskTitle.textContent = message.slice(0, 24);
  elements.taskSubtitle.textContent = "执行中";
  elements.input.value = "";
  resizeInput();
  setRunning(true);
  setStatus("正在连接 DeepSeek", "Starting");
  state.controller = new AbortController();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        session_id: state.sessionId,
        role: elements.roleSelect.value,
        model: elements.modelSelect.value,
      }),
      signal: state.controller.signal,
    });
    await consumeEventStream(response);
  } catch (error) {
    if (error.name === "AbortError") {
      updateAssistant("任务已在当前页面停止。");
      addActivity("error", "任务已停止", "客户端终止了事件流");
      setStatus("已停止", "Stopped");
      elements.taskSubtitle.textContent = "已停止";
    } else {
      updateAssistant(`连接服务失败：${error.message}`, true);
      addActivity("error", "连接失败", error.message);
      setStatus("连接失败", "Error");
    }
  } finally {
    state.controller = null;
    setRunning(false);
  }
}

async function resetTask() {
  if (state.running && state.controller) state.controller.abort();
  const oldSession = state.sessionId;
  state.sessionId = crypto.randomUUID();
  state.assistantNode = null;
  elements.messageList.replaceChildren();
  elements.emptyState.classList.remove("hidden");
  elements.taskTitle.textContent = "未命名任务";
  elements.taskSubtitle.textContent = "等待输入";
  clearActivity();
  const empty = document.createElement("div");
  empty.className = "activity-empty";
  empty.innerHTML =
    '<span class="activity-line"></span><p>等待任务</p>';
  elements.activityStream.append(empty);
  setStatus("准备就绪", "Idle");
  try {
    await fetch("/api/session/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: oldSession }),
    });
  } catch {
    // A local UI reset should still succeed if the server is temporarily unavailable.
  }
  elements.input.focus();
}

async function loadConfig() {
  try {
    const response = await fetch("/api/config");
    state.config = await response.json();
    elements.modelSelect.replaceChildren();
    state.config.allowed_models.forEach((model) => {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model;
      option.selected = model === state.config.model;
      elements.modelSelect.append(option);
    });
    elements.toolList.replaceChildren();
    state.config.tools.forEach((tool) => {
      const pill = document.createElement("span");
      pill.className = "tool-pill";
      pill.textContent = tool;
      pill.title = tool;
      elements.toolList.append(pill);
    });
    elements.thinkingMode.textContent = state.config.thinking_enabled
      ? `Thinking: ${state.config.reasoning_effort}`
      : "Thinking: off";
    elements.sidebarStatusDot.className = `status-dot ${state.config.ready ? "ready" : "error"}`;
    elements.sidebarStatusText.textContent = state.config.ready
      ? "DeepSeek 已连接"
      : "等待 API Key";
    if (!state.config.ready) {
      elements.configBanner.textContent =
        "未检测到 DEEPSEEK_API_KEY。设置环境变量并重启服务后，即可调用真实 DeepSeek 模型。";
      elements.configBanner.classList.remove("hidden");
    }
  } catch (error) {
    elements.configBanner.textContent = `无法读取服务配置：${error.message}`;
    elements.configBanner.classList.remove("hidden");
    elements.sidebarStatusDot.className = "status-dot error";
    elements.sidebarStatusText.textContent = "服务不可用";
  }
}

elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.running) {
    state.controller?.abort();
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

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.input.value = button.dataset.prompt;
    resizeInput();
    elements.input.focus();
  });
});

elements.newTask.addEventListener("click", resetTask);
elements.activityToggle.addEventListener("click", () => {
  elements.activityPanel.classList.add("open");
});
elements.closeActivity.addEventListener("click", () => {
  elements.activityPanel.classList.remove("open");
});

loadConfig();
elements.input.focus();
