const STORAGE_KEY = "my-agent-conversations-v1";

const state = {
  sessionId: "",
  running: false,
  controller: null,
  config: null,
  toolCalls: 0,
  rounds: 0,
  assistantNode: null,
  assistantPersisted: false,
  streamedAnswer: "",
  answerQueue: [],
  answerPlayback: null,
  answerPlaybackToken: 0,
  thinkingEnabled: false,
  reasoningEffort: null,
  thinkingChars: 0,
  reasoningText: "",
  reasoningNode: null,
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
  modelSelect: document.querySelector("#modelSelect"),
  thinkingSelect: document.querySelector("#thinkingSelect"),
  runStatus: document.querySelector("#runStatus"),
  configBanner: document.querySelector("#configBanner"),
  sidebarStatusDot: document.querySelector("#sidebarStatusDot"),
  sidebarStatusText: document.querySelector("#sidebarStatusText"),
  toolList: document.querySelector("#toolList"),
  activityPanel: document.querySelector("#activityPanel"),
  activityToggle: document.querySelector("#activityToggle"),
  closeActivity: document.querySelector("#closeActivity"),
  traceBackdrop: document.querySelector("#traceBackdrop"),
  activityStream: document.querySelector("#activityStream"),
  activityStatus: document.querySelector("#activityStatus"),
  toolCount: document.querySelector("#toolCount"),
  roundCount: document.querySelector("#roundCount"),
  chatHistory: document.querySelector("#chatHistory"),
  sidebar: document.querySelector("#sidebar"),
  sidebarToggle: document.querySelector("#sidebarToggle"),
  sidebarClose: document.querySelector("#sidebarClose"),
  sidebarScrim: document.querySelector("#sidebarScrim"),
};

/** 返回适合消息和 Trace 展示的当前时间。 */
function nowLabel() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

/** 将动态值格式化为可阅读的 JSON。 */
function prettyJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** 从本地存储恢复最近的对话列表。 */
function loadChats() {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    state.chats = Array.isArray(stored) ? stored.slice(0, 30) : [];
  } catch {
    state.chats = [];
  }
}

/** 保存最近对话，限制数量以避免本地存储无限增长。 */
function persistChats() {
  const ordered = [...state.chats]
    .sort((left, right) => right.updatedAt - left.updatedAt)
    .slice(0, 30);
  state.chats = ordered;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ordered));
}

/** 创建一条新的空对话记录。 */
function createChat() {
  const now = Date.now();
  return {
    id: crypto.randomUUID(),
    title: "新对话",
    status: "等待输入",
    updatedAt: now,
    messages: [],
  };
}

/** 返回当前选中的对话。 */
function activeChat() {
  return state.chats.find((chat) => chat.id === state.activeChatId) || null;
}

/** 确保页面始终存在一个可用的当前对话。 */
function ensureActiveChat() {
  if (!state.chats.length) {
    state.chats.push(createChat());
  }
  const savedId = localStorage.getItem(`${STORAGE_KEY}:active`);
  const selected = state.chats.find((chat) => chat.id === savedId) || state.chats[0];
  state.activeChatId = selected.id;
  state.sessionId = selected.id;
}

/** 根据更新时间给会话生成左侧分组。 */
function historyGroup(updatedAt) {
  const date = new Date(updatedAt);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return "今天";
  const difference = today.getTime() - date.getTime();
  return difference < 7 * 24 * 60 * 60 * 1000 ? "最近 7 天" : "更早";
}

/** 渲染左侧会话历史，并绑定会话切换事件。 */
function renderChatHistory() {
  elements.chatHistory.replaceChildren();
  if (!state.chats.length) {
    const empty = document.createElement("p");
    empty.className = "empty-history";
    empty.textContent = "还没有对话。";
    elements.chatHistory.append(empty);
    return;
  }

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
      button.dataset.chatId = chat.id;
      const title = document.createElement("strong");
      title.textContent = chat.title || "新对话";
      const status = document.createElement("small");
      status.textContent = chat.status || "等待输入";
      button.append(title, status);
      button.addEventListener("click", () => selectChat(chat.id));
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "history-delete-button";
      deleteButton.title = `删除会话：${chat.title || "新对话"}`;
      deleteButton.setAttribute("aria-label", deleteButton.title);
      deleteButton.disabled = state.running;
      deleteButton.innerHTML = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 7h14M9 7V4.8h6V7m-8 0 1 12h8l1-12M10 10.5v5M14 10.5v5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      deleteButton.addEventListener("click", () => deleteChat(chat.id));
      row.append(button, deleteButton);
      elements.chatHistory.append(row);
    });
}

/** 自动调整输入框高度并保持布局稳定。 */
function resizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 180)}px`;
}

/** 更新运行状态和发送按钮行为。 */
function setRunning(running) {
  state.running = running;
  elements.input.disabled = running;
  elements.modelSelect.disabled = running;
  elements.thinkingSelect.disabled = running;
  elements.chatHistory.querySelectorAll(".history-delete-button").forEach((button) => {
    button.disabled = running;
  });
  elements.sendButton.classList.toggle("running", running);
  elements.sendIcon.textContent = running ? "■" : "↑";
  elements.sendButton.title = running ? "停止" : "发送";
  elements.sendButton.setAttribute("aria-label", running ? "停止任务" : "发送消息");
  if (!running) {
    elements.input.disabled = false;
    elements.input.focus();
  }
}

/** 同步顶部状态与 Trace 状态。 */
function setStatus(text, status = "Idle") {
  elements.runStatus.textContent = text;
  elements.activityStatus.textContent = status;
}

/** 更新当前对话状态并刷新历史列表。 */
function setChatStatus(status) {
  const chat = activeChat();
  if (!chat) return;
  chat.status = status;
  chat.updatedAt = Date.now();
  persistChats();
  renderChatHistory();
}

/** 切换空会话的页面级滚动锁，避免欢迎页出现浏览器滚动条。 */
function setEmptyConversationMode(isEmpty) {
  elements.conversation.classList.toggle("is-empty", isEmpty);
  document.querySelector(".chat-main")?.classList.toggle("is-empty", isEmpty);
  document.documentElement.classList.toggle("is-empty-chat", isEmpty);
  document.body.classList.toggle("is-empty-chat", isEmpty);
}

/** 显示对话列表并隐藏空状态。 */
function showConversation() {
  elements.emptyState.classList.add("hidden");
  setEmptyConversationMode(false);
}

/** 把受支持的 Markdown 行内语法转换为安全 DOM 节点。 */
function appendInlineMarkdown(container, content) {
  const pattern = /`([^`\n]+)`|\*\*([^*\n]+)\*\*|\*([^*\n]+)\*|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g;
  let cursor = 0;
  for (const match of content.matchAll(pattern)) {
    if (match.index > cursor) {
      container.append(document.createTextNode(content.slice(cursor, match.index)));
    }
    if (match[1] !== undefined) {
      const code = document.createElement("code");
      code.textContent = match[1];
      container.append(code);
    } else if (match[2] !== undefined) {
      const strong = document.createElement("strong");
      strong.textContent = match[2];
      container.append(strong);
    } else if (match[3] !== undefined) {
      const emphasis = document.createElement("em");
      emphasis.textContent = match[3];
      container.append(emphasis);
    } else {
      const link = document.createElement("a");
      link.textContent = match[4];
      link.href = match[5];
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      container.append(link);
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < content.length) {
    container.append(document.createTextNode(content.slice(cursor)));
  }
}

/** 将基础 Markdown 块语法渲染到消息节点，不执行模型提供的 HTML。 */
function renderMarkdown(container, content) {
  container.replaceChildren();
  const lines = String(content || "").replace(/\r\n/g, "\n").split("\n");
  let codeBlock = null;
  let activeList = null;
  let activeListType = "";

  for (const line of lines) {
    const fence = line.match(/^\s*```/);
    if (fence) {
      activeList = null;
      activeListType = "";
      if (codeBlock) {
        codeBlock = null;
      } else {
        const pre = document.createElement("pre");
        codeBlock = document.createElement("code");
        pre.append(codeBlock);
        container.append(pre);
      }
      continue;
    }

    if (codeBlock) {
      codeBlock.textContent += `${codeBlock.textContent ? "\n" : ""}${line}`;
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    const unorderedItem = line.match(/^\s*[-+*]\s+(.+)$/);
    const orderedItem = line.match(/^\s*\d+[.)]\s+(.+)$/);
    const quote = line.match(/^\s*>\s?(.*)$/);

    if (heading) {
      activeList = null;
      activeListType = "";
      const headingNode = document.createElement(`h${heading[1].length}`);
      appendInlineMarkdown(headingNode, heading[2]);
      container.append(headingNode);
      continue;
    }

    if (unorderedItem || orderedItem) {
      const listType = unorderedItem ? "ul" : "ol";
      if (!activeList || activeListType !== listType) {
        activeList = document.createElement(listType);
        activeListType = listType;
        container.append(activeList);
      }
      const item = document.createElement("li");
      appendInlineMarkdown(item, (unorderedItem || orderedItem)[1]);
      activeList.append(item);
      continue;
    }

    activeList = null;
    activeListType = "";
    if (quote) {
      const quoteNode = document.createElement("blockquote");
      appendInlineMarkdown(quoteNode, quote[1]);
      container.append(quoteNode);
      continue;
    }
    if (!line) {
      const spacer = document.createElement("div");
      spacer.className = "markdown-spacer";
      container.append(spacer);
      continue;
    }
    const paragraph = document.createElement("div");
    paragraph.className = "markdown-paragraph";
    appendInlineMarkdown(paragraph, line);
    container.append(paragraph);
  }
}

/** 创建明确标注为模型生成内容的可折叠深度思考区域。 */
function createReasoningPanel(content, effort = "high") {
  const details = document.createElement("details");
  details.className = "reasoning-panel";
  details.open = true;
  const summary = document.createElement("summary");
  summary.textContent = `DeepSeek 深度思考 · ${effort}`;
  const notice = document.createElement("div");
  notice.className = "reasoning-notice";
  notice.textContent = "以下为模型生成的思考过程，可能存在错误。";
  const reasoningContent = document.createElement("div");
  reasoningContent.className = "reasoning-content";
  reasoningContent.textContent = content;
  details.append(summary, notice, reasoningContent);
  return { details, summary, content: reasoningContent };
}

/** 构建一条用户或助手消息节点。 */
function createMessageNode(
  role,
  content,
  pending = false,
  reasoningContent = "",
  reasoningEffort = "high",
) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "assistant-avatar";
    avatar.textContent = "M";
    article.append(avatar);
  }

  const body = document.createElement("div");
  body.className = "message-body";
  const heading = document.createElement("div");
  heading.className = "message-heading";
  const name = document.createElement("strong");
  name.textContent = role === "user" ? "你" : "My-Agent";
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
    if (role === "assistant") {
      renderMarkdown(text, content);
    } else {
      text.textContent = content;
    }
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";
  body.append(heading);
  let reasoning = null;
  if (role === "assistant" && reasoningContent) {
    reasoning = createReasoningPanel(reasoningContent, reasoningEffort);
    body.append(reasoning.details);
  }
  body.append(text, meta);
  article.append(body);
  return { article, body, text, meta, reasoning };
}

/** 将消息写入当前对话，并按需持久化到本地历史。 */
function addMessage(role, content, { pending = false, persist = true } = {}) {
  showConversation();
  const node = createMessageNode(role, content, pending);
  elements.messageList.append(node.article);
  elements.conversation.scrollTop = elements.conversation.scrollHeight;

  if (persist) {
    const chat = activeChat();
    if (chat) {
      chat.messages.push({ role, content });
      if (role === "user" && chat.title === "新对话") {
        chat.title = content.slice(0, 28);
      }
      chat.updatedAt = Date.now();
      persistChats();
      renderChatHistory();
      elements.taskTitle.textContent = chat.title;
    }
  }
  return node;
}

/** 保存最终助手消息，避免同一轮被重复写入历史。 */
function persistAssistantMessage(content) {
  if (state.assistantPersisted) return;
  const chat = activeChat();
  if (!chat) return;
  const message = { role: "assistant", content };
  if (state.reasoningText) {
    message.reasoning_content = state.reasoningText;
    message.reasoning_effort = state.reasoningEffort || "high";
  }
  chat.messages.push(message);
  chat.updatedAt = Date.now();
  state.assistantPersisted = true;
  persistChats();
  renderChatHistory();
}

/** 用最终结果替换助手等待状态。 */
function updateAssistant(content, isError = false) {
  if (!state.assistantNode) {
    state.assistantNode = addMessage("assistant", content, { persist: false });
  } else {
    state.assistantNode.text.classList.remove("pending");
    renderMarkdown(state.assistantNode.text, content);
  }
  state.assistantNode.text.classList.toggle("error-text", isError);
  persistAssistantMessage(content);
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

/** 等待指定毫秒数，让浏览器在两个字符之间完成绘制。 */
function waitForCharacterInterval(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

/** 把一个字符追加到当前回答，保持滚动位置跟随最新内容。 */
function appendAssistantCharacter(character) {
  if (!state.assistantNode) {
    state.assistantNode = addMessage("assistant", "", { persist: false });
  }
  if (!state.streamedAnswer) {
    state.assistantNode.text.classList.remove("pending");
    state.assistantNode.text.replaceChildren();
  }
  state.streamedAnswer += character;
  renderMarkdown(state.assistantNode.text, state.streamedAnswer);
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

/** 按固定节奏播放已接收字符，避免快速到达的分片成批渲染。 */
async function playAssistantQueue(playbackToken) {
  while (state.answerQueue.length && playbackToken === state.answerPlaybackToken) {
    const character = state.answerQueue.shift();
    appendAssistantCharacter(character);
    await waitForCharacterInterval(20);
  }
}

/** 在播放器空闲且队列有内容时启动逐字播放。 */
function startAssistantPlayback() {
  if (state.answerPlayback || !state.answerQueue.length) return;
  const playbackToken = state.answerPlaybackToken;
  state.answerPlayback = playAssistantQueue(playbackToken).finally(() => {
    if (playbackToken !== state.answerPlaybackToken) return;
    state.answerPlayback = null;
    startAssistantPlayback();
  });
}

/** 将公开回答分片放入独立播放队列，不阻塞网络流继续读取。 */
function enqueueAssistantDelta(delta) {
  if (!delta) return;
  state.answerQueue.push(...Array.from(delta));
  startAssistantPlayback();
}

/** 等待已经接收的字符全部显示后再处理最终事件。 */
async function waitForAssistantPlayback() {
  while (state.answerPlayback) {
    await state.answerPlayback;
  }
}

/** 停止旧回答的字符播放并清空尚未显示的内容。 */
function resetAssistantPlayback() {
  state.answerPlaybackToken += 1;
  state.answerQueue = [];
  state.answerPlayback = null;
  state.streamedAnswer = "";
  state.reasoningText = "";
  state.reasoningNode = null;
}

/** 更新等待状态文案，同时保留正在跳动的思考指示器。 */
function updatePendingAssistant(label) {
  if (!state.assistantNode?.text.classList.contains("pending")) return;
  const labelNode = state.assistantNode.text.querySelector(".thinking-label");
  if (labelNode) labelNode.textContent = label;
}

/** 获取或创建当前回答的深度思考面板。 */
function ensureReasoningPanel() {
  if (state.reasoningNode) return state.reasoningNode;
  if (!state.assistantNode) return null;
  const reasoning = createReasoningPanel("", state.reasoningEffort || "high");
  state.assistantNode.body.insertBefore(reasoning.details, state.assistantNode.text);
  state.reasoningNode = reasoning;
  return reasoning;
}

/** 为当前助手消息添加简短运行元数据。 */
function addMeta(label) {
  if (!state.assistantNode) return;
  const chip = document.createElement("span");
  chip.className = "meta-chip";
  chip.textContent = label;
  state.assistantNode.meta.append(chip);
}

/** 清空上一轮 Trace 事件和统计。 */
function clearActivity() {
  state.toolCalls = 0;
  state.rounds = 0;
  elements.toolCount.textContent = "0";
  elements.roundCount.textContent = "0";
  elements.activityStream.replaceChildren();
}

/** 向 Trace 抽屉追加一条结构化事件。 */
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

/** 根据服务端事件按到达顺序更新对话、状态和 Trace。 */
async function handleAgentEvent(event) {
  switch (event.type) {
    case "started":
      state.thinkingEnabled = Boolean(event.thinking_enabled);
      state.reasoningEffort = event.reasoning_effort || null;
      state.thinkingChars = 0;
      setStatus(`请求 ${event.request_id.slice(0, 8)} · ${event.model}`, "Running");
      addActivity(
        "model",
        "任务已开始",
        event.model,
        [
          "request",
          event.thinking_enabled
            ? `thinking:${event.reasoning_effort || "high"}`
            : "thinking:disabled",
        ],
      );
      break;
    case "thinking_delta":
      const reasoningDelta = String(event.delta || "");
      state.reasoningText += reasoningDelta;
      state.thinkingChars += Number(event.delta_chars || Array.from(reasoningDelta).length);
      const reasoningPanel = ensureReasoningPanel();
      if (reasoningPanel) {
        reasoningPanel.content.textContent = state.reasoningText;
        reasoningPanel.summary.textContent =
          `DeepSeek 深度思考 · ${state.reasoningEffort || "high"} · ${state.thinkingChars} 字符`;
      }
      updatePendingAssistant(
        `正在深度思考 · ${state.reasoningEffort || "high"} · ${state.thinkingChars} 字符`,
      );
      setStatus(`DeepSeek 正在深度思考 · ${state.thinkingChars} 字符`, "Thinking");
      elements.conversation.scrollTop = elements.conversation.scrollHeight;
      break;
    case "intent": {
      const confidence = Math.round((event.confidence || 0) * 100);
      addActivity(
        "intent",
        "意图识别完成",
        event.needs_clarification
          ? event.clarification_question || "模型建议澄清"
          : "已提取目标、实体和候选工具",
        [...(event.intents || []), `confidence:${confidence}%`],
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
    case "tool_call":
      state.toolCalls += 1;
      elements.toolCount.textContent = String(state.toolCalls);
      setStatus(`正在调用 ${event.name}`, "Tool");
      addActivity("tool", event.name, "工具参数已进入服务端注册表", ["running"], event.arguments);
      break;
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
    case "answer_delta":
      enqueueAssistantDelta(event.delta || "");
      setStatus("DeepSeek 正在生成回答", "Streaming");
      break;
    case "final": {
      await waitForAssistantPlayback();
      const finalAnswer = event.answer || state.streamedAnswer;
      state.streamedAnswer = finalAnswer;
      updateAssistant(finalAnswer);
      const totalTokens = event.usage?.total_tokens;
      if (totalTokens) addMeta(`${totalTokens} tokens`);
      if (state.thinkingEnabled) {
        addMeta(
          `深度思考 · ${state.reasoningEffort || "high"} · ${state.thinkingChars} 字符`,
        );
      }
      addMeta(`${state.rounds} rounds`);
      addActivity(
        "final",
        "结果已返回",
        event.finish_reason ? `finish: ${event.finish_reason}` : "模型完成任务",
        totalTokens ? [`tokens:${totalTokens}`] : [],
      );
      setStatus("任务完成", "Done");
      setChatStatus("已完成");
      break;
    }
    case "error":
      resetAssistantPlayback();
      updateAssistant(event.message || "任务执行失败。", true);
      addActivity("error", "任务失败", event.message || "未知错误");
      setStatus("执行失败", "Error");
      setChatStatus("失败");
      break;
    default:
      break;
  }
}

/** 解析一个标准 SSE 事件块。 */
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

/** 持续读取 SSE 响应并分发完整事件。 */
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
    for (const block of blocks) {
      const event = parseEventBlock(block);
      if (event) await handleAgentEvent(event);
    }
  }
  if (buffer.trim()) {
    const event = parseEventBlock(buffer);
    if (event) await handleAgentEvent(event);
  }
}

/** 发送一条用户消息并消费后端流式响应。 */
async function sendTask(message) {
  if (!state.config?.ready) {
    state.assistantPersisted = false;
    state.assistantNode = addMessage("assistant", "正在检查服务配置", { pending: true, persist: false });
    updateAssistant("尚未配置 DEEPSEEK_API_KEY，请先完成服务端配置。", true);
    return;
  }

  clearActivity();
  state.assistantNode = null;
  state.assistantPersisted = false;
  resetAssistantPlayback();
  addMessage("user", message);
  const isThinkingEnabled = elements.thinkingSelect.value !== "disabled";
  state.assistantNode = addMessage(
    "assistant",
    isThinkingEnabled ? "正在深度思考" : "正在生成回答",
    { pending: true, persist: false },
  );
  elements.input.value = "";
  resizeInput();
  setRunning(true);
  setStatus("正在连接 DeepSeek", "Starting");
  setChatStatus("执行中");
  state.controller = new AbortController();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        session_id: state.sessionId,
        role: "standard",
        model: elements.modelSelect.value,
        thinking_enabled: elements.thinkingSelect.value !== "disabled",
        reasoning_effort:
          elements.thinkingSelect.value === "disabled"
            ? null
            : elements.thinkingSelect.value,
      }),
      signal: state.controller.signal,
    });
    await consumeEventStream(response);
  } catch (error) {
    if (error.name === "AbortError") {
      resetAssistantPlayback();
      updateAssistant("任务已在当前页面停止。 ");
      addActivity("error", "任务已停止", "客户端终止了事件流");
      setStatus("已停止", "Stopped");
      setChatStatus("已停止");
    } else {
      updateAssistant(`连接服务失败：${error.message}`, true);
      addActivity("error", "连接失败", error.message);
      setStatus("连接失败", "Error");
      setChatStatus("连接失败");
    }
  } finally {
    state.controller = null;
    setRunning(false);
  }
}

/** 将当前对话内容恢复到主对话区。 */
function renderActiveChat() {
  const chat = activeChat();
  elements.messageList.replaceChildren();
  state.assistantNode = null;
  state.assistantPersisted = false;
  resetAssistantPlayback();
  elements.taskTitle.textContent = chat?.title || "新对话";
  setStatus(chat?.status || "准备就绪", "Idle");

  if (!chat || !chat.messages.length) {
    elements.emptyState.classList.remove("hidden");
    setEmptyConversationMode(true);
    return;
  }

  elements.emptyState.classList.add("hidden");
  setEmptyConversationMode(false);
  chat.messages.forEach((message) => {
    const node = createMessageNode(
      message.role,
      message.content,
      false,
      message.reasoning_content || "",
      message.reasoning_effort || "high",
    );
    elements.messageList.append(node.article);
  });
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

/** 选择指定历史会话并恢复其本地消息。 */
function selectChat(chatId) {
  if (state.running || chatId === state.activeChatId) return;
  const chat = state.chats.find((item) => item.id === chatId);
  if (!chat) return;
  state.activeChatId = chat.id;
  state.sessionId = chat.id;
  localStorage.setItem(`${STORAGE_KEY}:active`, chat.id);
  clearActivity();
  renderChatHistory();
  renderActiveChat();
  closeSidebar();
  elements.input.focus();
}

/** 经用户确认后删除服务端会话，并同步移除浏览器中的本地对话。 */
async function deleteChat(chatId) {
  if (state.running) return;
  const chat = state.chats.find((item) => item.id === chatId);
  if (!chat) return;
  const confirmed = window.confirm(
    `确定删除“${chat.title || "新对话"}”吗？会话内容和审计事件将无法恢复。`,
  );
  if (!confirmed) return;

  try {
    const response = await fetch(`/api/session/${encodeURIComponent(chatId)}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  } catch (error) {
    window.alert(`删除会话失败：${error.message}`);
    return;
  }

  const wasActive = chatId === state.activeChatId;
  state.chats = state.chats.filter((item) => item.id !== chatId);
  if (!state.chats.length) state.chats.push(createChat());
  persistChats();

  if (!wasActive) {
    renderChatHistory();
    return;
  }

  const nextChat = state.chats[0];
  state.activeChatId = nextChat.id;
  state.sessionId = nextChat.id;
  localStorage.setItem(`${STORAGE_KEY}:active`, nextChat.id);
  clearActivity();
  renderChatHistory();
  renderActiveChat();
  elements.input.focus();
}

/** 判断会话是否仍是可复用的无内容“新对话”，兼容旧版本地记录。 */
function isReusableEmptyChat(chat) {
  const messages = Array.isArray(chat.messages) ? chat.messages : [];
  return messages.length === 0 && (chat.status === "等待输入" || chat.title === "新对话");
}

/** 返回更新时间最新的未使用会话，作为新建按钮的唯一复用目标。 */
function findReusableEmptyChat() {
  return state.chats
    .filter(isReusableEmptyChat)
    .sort((left, right) => right.updatedAt - left.updatedAt)[0] || null;
}

/** 合并旧版本遗留的重复空会话，保留最新一条并维护当前会话选择。 */
function collapseDuplicateEmptyChats() {
  const reusableChat = findReusableEmptyChat();
  if (!reusableChat) return;

  const emptyChats = state.chats.filter(isReusableEmptyChat);
  if (emptyChats.length < 2) return;

  const savedChatId = localStorage.getItem(`${STORAGE_KEY}:active`);
  state.chats = state.chats.filter(
    (chat) => !isReusableEmptyChat(chat) || chat.id === reusableChat.id,
  );
  if (emptyChats.some((chat) => chat.id === savedChatId)) {
    localStorage.setItem(`${STORAGE_KEY}:active`, reusableChat.id);
  }
  persistChats();
}

/** 创建或复用空会话，确保“新建对话”在全局范围内保持幂等。 */
function createNewTask() {
  const reusableChat = findReusableEmptyChat();
  if (reusableChat) {
    if (state.running && state.controller) state.controller.abort();
    state.activeChatId = reusableChat.id;
    state.sessionId = reusableChat.id;
    localStorage.setItem(`${STORAGE_KEY}:active`, reusableChat.id);
    persistChats();
    clearActivity();
    renderChatHistory();
    renderActiveChat();
    closeSidebar();
    elements.input.focus();
    return;
  }

  if (state.running && state.controller) state.controller.abort();
  const newChat = createChat();
  state.chats.unshift(newChat);
  state.activeChatId = newChat.id;
  state.sessionId = newChat.id;
  localStorage.setItem(`${STORAGE_KEY}:active`, newChat.id);
  persistChats();
  clearActivity();
  renderChatHistory();
  renderActiveChat();
  closeSidebar();
  elements.input.focus();
}

/** 打开右侧 Trace 抽屉。 */
function openTrace() {
  elements.activityPanel.classList.add("open");
  elements.traceBackdrop.classList.add("open");
}

/** 关闭右侧 Trace 抽屉。 */
function closeTrace() {
  elements.activityPanel.classList.remove("open");
  elements.traceBackdrop.classList.remove("open");
}

/** 在窄屏设备上打开左侧会话栏。 */
function openSidebar() {
  elements.sidebar.classList.add("open");
  elements.sidebarScrim.classList.add("open");
}

/** 在窄屏设备上关闭左侧会话栏。 */
function closeSidebar() {
  elements.sidebar.classList.remove("open");
  elements.sidebarScrim.classList.remove("open");
}

/** 从服务端加载模型、工具和连接状态。 */
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
    const supportedEfforts = Array.isArray(state.config.reasoning_efforts)
      ? state.config.reasoning_efforts
      : ["low", "high", "max"];
    const configuredEffort = supportedEfforts.includes(state.config.reasoning_effort)
      ? state.config.reasoning_effort
      : "high";
    elements.thinkingSelect.value = state.config.thinking_enabled
      ? configuredEffort
      : "disabled";
    elements.sidebarStatusDot.className = `status-dot ${state.config.ready ? "ready" : "error"}`;
    elements.sidebarStatusText.textContent = state.config.ready
      ? "DeepSeek 已连接"
      : "等待 API Key";
    if (!state.config.ready) {
      elements.configBanner.textContent =
        "未检测到 DEEPSEEK_API_KEY。完成服务端配置后即可调用真实 DeepSeek 模型。";
      elements.configBanner.classList.remove("hidden");
    }
  } catch (error) {
    elements.configBanner.textContent = `无法读取服务配置：${error.message}`;
    elements.configBanner.classList.remove("hidden");
    elements.sidebarStatusDot.className = "status-dot error";
    elements.sidebarStatusText.textContent = "服务不可用";
  }
}

/** 初始化对话、配置和页面事件。 */
function initialize() {
  loadChats();
  collapseDuplicateEmptyChats();
  ensureActiveChat();
  renderChatHistory();
  renderActiveChat();
  loadConfig();
  elements.input.focus();
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

elements.newTask.addEventListener("click", createNewTask);
elements.activityToggle.addEventListener("click", openTrace);
elements.closeActivity.addEventListener("click", closeTrace);
elements.traceBackdrop.addEventListener("click", closeTrace);
elements.sidebarToggle.addEventListener("click", openSidebar);
elements.sidebarClose.addEventListener("click", closeSidebar);
elements.sidebarScrim.addEventListener("click", closeSidebar);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeTrace();
    closeSidebar();
  }
});

initialize();
