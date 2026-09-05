import {
  Box,
  CirclePlus,
  FileText,
  Folder,
  PanelLeftClose,
  SquareTerminal,
  Trash2,
} from "lucide-react";

import { historyGroup } from "../domain/chat";
import type { ChatThread, PublicConfig } from "../domain/types";

interface SidebarProps {
  chats: ChatThread[];
  activeChatId: string;
  config: PublicConfig | null;
  projectName: string;
  isOpen: boolean;
  isRunning: boolean;
  onClose: () => void;
  onCreate: () => void;
  onSelect: (chatId: string) => void;
  onRemove: (chatId: string) => void;
}

/** 展示本地 Thread 导航和当前模型连接状态。 */
export function Sidebar({
  chats,
  activeChatId,
  config,
  projectName,
  isOpen,
  isRunning,
  onClose,
  onCreate,
  onSelect,
  onRemove,
}: SidebarProps) {
  let previousGroup = "";

  return (
    <>
      <aside
        className={`sidebar${isOpen ? " is-open" : ""}`}
        aria-label="任务导航"
        aria-hidden={isOpen ? false : undefined}
      >
        <div className="sidebar__header">
          <div className="brand">
            <span className="brand__mark" aria-hidden="true">
              <Box size={21} strokeWidth={2} />
            </span>
            <span>Coding-Harness</span>
          </div>
          <button
            className="icon-button sidebar__close"
            type="button"
            onClick={onClose}
            aria-label="关闭任务导航"
            title="关闭任务导航"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>

        <button
          className="new-task-button"
          type="button"
          onClick={onCreate}
          disabled={isRunning}
          aria-describedby={isRunning ? "running-task-lock" : undefined}
          aria-label="新建任务"
        >
          <CirclePlus size={18} />
          <span>新建任务</span>
        </button>

        <p className="sidebar-section-title">最近任务</p>
        <nav className="thread-list" aria-label="最近任务">
          {chats.map((chat) => {
            const group = historyGroup(chat.updatedAt);
            const showGroup = group !== previousGroup;
            previousGroup = group;
            return (
              <div className="thread-entry" key={chat.id}>
                {showGroup ? (
                  <p className="thread-entry__group">{group}</p>
                ) : null}
                <div className="thread-entry__row">
                  <button
                    className={`thread-button${
                      chat.id === activeChatId ? " is-active" : ""
                    }`}
                    type="button"
                    disabled={isRunning && chat.id !== activeChatId}
                    aria-current={chat.id === activeChatId ? "true" : undefined}
                    aria-describedby={
                      isRunning && chat.id !== activeChatId
                        ? "running-task-lock"
                        : undefined
                    }
                    onClick={() => onSelect(chat.id)}
                  >
                    <FileText
                      className="thread-button__icon"
                      size={15}
                      aria-hidden="true"
                    />
                    <span className="thread-button__copy">
                      <span>{chat.title}</span>
                      <small>{chat.status}</small>
                    </span>
                  </button>
                  <button
                    className="icon-button thread-entry__remove"
                    type="button"
                    disabled={isRunning}
                    aria-describedby={isRunning ? "running-task-lock" : undefined}
                    onClick={() => onRemove(chat.id)}
                    aria-label={`移除任务：${chat.title}`}
                    title={`移除任务：${chat.title}`}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            );
          })}
        </nav>

        <section className="project-section" aria-label="当前项目">
          <p className="sidebar-section-title">项目</p>
          <div className="project-entry" title={config?.workspace_root ?? ""}>
            <span className="project-entry__icon" aria-hidden="true">
              <Folder size={17} />
            </span>
            <span>{projectName}</span>
          </div>
          <div className="project-scope">
            <SquareTerminal size={14} aria-hidden="true" />
            <span>Workspace 执行边界</span>
          </div>
        </section>

        <footer className="sidebar__footer">
          <span
            className={`connection-dot${
              config ? (config.ready ? " is-ready" : " is-error") : ""
            }`}
            aria-hidden="true"
          />
          <div>
            <strong>
              {config
                ? config.ready
                  ? "Harness 已就绪"
                  : "等待模型配置"
                : "正在连接"}
            </strong>
            <span>{config?.model ?? "读取配置中"}</span>
          </div>
        </footer>
        <span className="sr-only" id="running-task-lock">
          当前 Turn 运行期间不可新建、切换或移除任务
        </span>
      </aside>
      <button
        className={`scrim sidebar-scrim${isOpen ? " is-open" : ""}`}
        type="button"
        onClick={onClose}
        aria-label="关闭任务导航"
      />
    </>
  );
}
