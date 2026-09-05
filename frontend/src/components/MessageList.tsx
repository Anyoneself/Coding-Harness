import { Bot, UserRound } from "lucide-react";

import type { ChatMessage, ExecutionState } from "../domain/types";
import { renderSafeMarkdown } from "../lib/markdown";

interface MessageListProps {
  messages: ChatMessage[];
  execution: ExecutionState;
  showLiveAssistant: boolean;
  projectName: string;
}

/** 展示已持久化消息和当前尚未收敛的流式回答。 */
export function MessageList({
  messages,
  execution,
  showLiveAssistant,
  projectName,
}: MessageListProps) {
  if (!messages.length && !showLiveAssistant) {
    return (
      <div className="empty-state">
        <span className="empty-state__mark" aria-hidden="true">
          <Bot size={28} />
        </span>
        <p className="empty-state__project">{projectName}</p>
        <h1>你想让我们在 Coding-Harness 中构建什么？</h1>
      </div>
    );
  }

  return (
    <div className="message-list">
      {messages.map((message) => (
        <Message key={message.id} message={message} />
      ))}
      {showLiveAssistant ? (
        <LiveAssistant
          content={execution.answer}
          error={execution.error}
          statusLabel={execution.statusLabel}
        />
      ) : null}
    </div>
  );
}

/** 渲染一条已经进入本地公开历史的消息。 */
function Message({ message }: { message: ChatMessage }) {
  const isAssistant = message.role === "assistant";
  return (
    <article className={`message message--${message.role}`}>
      {isAssistant ? (
        <span className="message__avatar" aria-hidden="true">
          <Bot size={16} />
        </span>
      ) : null}
      <div className={`message__body${message.isError ? " is-error" : ""}`}>
        {isAssistant ? (
          <div className="message__heading">
            <strong>Coding-Harness</strong>
            <time>{formatMessageTime(message.createdAt)}</time>
          </div>
        ) : (
          <span className="message__user-icon" aria-hidden="true">
            <UserRound size={14} />
          </span>
        )}
        {isAssistant ? (
          <div
            className="markdown-content"
            dangerouslySetInnerHTML={{
              __html: renderSafeMarkdown(message.content),
            }}
          />
        ) : (
          <p className="user-content">{message.content}</p>
        )}
      </div>
    </article>
  );
}

/** 渲染当前 Turn 的增量回答或等待动画。 */
function LiveAssistant({
  content,
  error,
  statusLabel,
}: {
  content: string;
  error: string;
  statusLabel: string;
}) {
  const visibleContent = error || content;
  return (
    <article className="message message--assistant" aria-live="polite">
      <span className="message__avatar is-live" aria-hidden="true">
        <Bot size={16} />
      </span>
      <div className={`message__body${error ? " is-error" : ""}`}>
        <div className="message__heading">
          <strong>Coding-Harness</strong>
          <span className="live-label">{statusLabel}</span>
        </div>
        {visibleContent ? (
          <div
            className="markdown-content"
            dangerouslySetInnerHTML={{
              __html: renderSafeMarkdown(visibleContent),
            }}
          />
        ) : (
          <div className="thinking" aria-label={statusLabel}>
            <span />
            <span />
            <span />
          </div>
        )}
      </div>
    </article>
  );
}

/** 按当前区域格式化消息时间，不持久化展示字符串。 */
function formatMessageTime(timestamp: number): string {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp));
}
