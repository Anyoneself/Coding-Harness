import {
  Box,
  PanelLeft,
  PanelRight,
  RotateCcw,
} from "lucide-react";
import type { RefObject } from "react";

import type { WorkbenchView } from "../domain/types";

interface TopNavigationProps {
  activeView: WorkbenchView;
  canClearInspector: boolean;
  onSelectView: (view: WorkbenchView) => void;
  onOpenSidebar: () => void;
  onOpenInspector: () => void;
  onClearInspector: () => void;
  sidebarTriggerRef: RefObject<HTMLButtonElement | null>;
  inspectorTriggerRef: RefObject<HTMLButtonElement | null>;
}

const navigationItems: Array<{
  view: WorkbenchView;
  label: string;
}> = [
  { view: "workspace", label: "工作台" },
  { view: "events", label: "执行事件" },
  { view: "turn", label: "Turn" },
];

/** 展示只映射现有工作台、Event 和 Turn 能力的产品顶栏。 */
export function TopNavigation({
  activeView,
  canClearInspector,
  onSelectView,
  onOpenSidebar,
  onOpenInspector,
  onClearInspector,
  sidebarTriggerRef,
  inspectorTriggerRef,
}: TopNavigationProps) {
  return (
    <header className="top-navigation">
      <div className="top-navigation__leading">
        <button
          ref={sidebarTriggerRef}
          className="icon-button mobile-control"
          type="button"
          onClick={onOpenSidebar}
          aria-label="打开任务导航"
          title="打开任务导航"
        >
          <PanelLeft size={19} />
        </button>
        <div className="top-navigation__mobile-brand">
          <Box size={20} aria-hidden="true" />
          <span>Coding-Harness</span>
        </div>
      </div>

      <nav className="primary-navigation" aria-label="主导航">
        {navigationItems.map(({ view, label }) => (
          <button
            key={view}
            className={activeView === view ? "is-active" : ""}
            type="button"
            aria-current={activeView === view ? "page" : undefined}
            onClick={() => onSelectView(view)}
          >
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="top-navigation__context">
        {canClearInspector ? (
          <button
            className="icon-button"
            type="button"
            onClick={onClearInspector}
            aria-label="清空检查器"
            title="清空检查器"
          >
            <RotateCcw size={17} />
          </button>
        ) : null}
        <button
          ref={inspectorTriggerRef}
          className="icon-button inspector-toggle"
          type="button"
          onClick={onOpenInspector}
          aria-label="打开执行检查器"
          title="打开执行检查器"
        >
          <PanelRight size={19} />
        </button>
      </div>
    </header>
  );
}
