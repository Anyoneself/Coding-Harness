import { Braces, ListTree, PanelRightClose } from "lucide-react";

import type { ExecutionState } from "../domain/types";

interface InspectorProps {
  execution: ExecutionState;
  isOpen: boolean;
  activeTab: InspectorTab;
  onClose: () => void;
  onTabChange: (tab: InspectorTab) => void;
}

export type InspectorTab = "events" | "turn";

/** 展示 Turn 事件时间线和当前稳定元数据。 */
export function Inspector({
  execution,
  isOpen,
  activeTab,
  onClose,
  onTabChange,
}: InspectorProps) {
  return (
    <>
      <aside
        className={`inspector${isOpen ? " is-open" : ""}`}
        aria-label="Turn 检查器"
        aria-hidden={!isOpen}
      >
        <div className="inspector__header">
          <div>
            <span className="eyebrow">TURN INSPECTOR</span>
            <strong>执行检查器</strong>
          </div>
          <button
            className="icon-button inspector__close"
            type="button"
            onClick={onClose}
            aria-label="关闭执行检查器"
            title="关闭执行检查器"
          >
            <PanelRightClose size={18} />
          </button>
        </div>
        <div className="inspector-tabs" role="tablist" aria-label="检查器视图">
          <button
            type="button"
            role="tab"
            aria-label="事件"
            aria-selected={activeTab === "events"}
            className={activeTab === "events" ? "is-active" : ""}
            onClick={() => onTabChange("events")}
          >
            <ListTree size={15} />
            事件
            <span>{execution.events.length}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "turn"}
            className={activeTab === "turn" ? "is-active" : ""}
            onClick={() => onTabChange("turn")}
          >
            <Braces size={15} />
            Turn
          </button>
        </div>

        {activeTab === "events" ? (
          <EventTimeline execution={execution} />
        ) : (
          <TurnDetails execution={execution} />
        )}
      </aside>
      <button
        className={`scrim inspector-scrim${isOpen ? " is-open" : ""}`}
        type="button"
        onClick={onClose}
        aria-label="关闭执行检查器"
      />
    </>
  );
}

/** 按序展示所有公开事件，未知事件仍保留原始类型。 */
function EventTimeline({ execution }: { execution: ExecutionState }) {
  if (!execution.events.length) {
    return (
      <div className="inspector-empty">
        <ListTree size={22} />
        <strong>暂无执行事件</strong>
        <span>Turn 创建后，公开事件会按序出现在这里。</span>
      </div>
    );
  }
  return (
    <div className="event-timeline">
      {execution.events.map((event) => (
        <article className="event-row" key={`${event.sequence}-${event.type}`}>
          <span className={`event-row__dot is-${event.tone}`} aria-hidden="true" />
          <div>
            <header>
              <strong>{event.title}</strong>
              <span>#{event.sequence}</span>
            </header>
            <code>{event.type}</code>
            {event.detail ? <p>{event.detail}</p> : null}
          </div>
        </article>
      ))}
    </div>
  );
}

/** 展示当前 Turn 的稳定状态、序号和公开用量。 */
function TurnDetails({ execution }: { execution: ExecutionState }) {
  const rows = [
    ["状态", execution.statusLabel],
    ["Turn ID", execution.turnId || "尚未创建"],
    ["事件序号", String(execution.lastSequence)],
    ["公开事件", String(execution.events.length)],
    [
      "Token",
      execution.totalTokens === null ? "暂无" : String(execution.totalTokens),
    ],
  ];
  return (
    <dl className="turn-details">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
