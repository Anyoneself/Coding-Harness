import { ArrowUp, Folder, Square, TerminalSquare } from "lucide-react";
import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

interface ComposerProps {
  isRunning: boolean;
  isReady: boolean;
  isUnavailable: boolean;
  model: string;
  projectName: string;
  onSubmit: (message: string) => void;
  onInterrupt: () => void;
  onNeedsConfiguration: () => void;
}

/** 提供任务输入、自动扩展和运行中断控制。 */
export function Composer({
  isRunning,
  isReady,
  isUnavailable,
  model,
  projectName,
  onSubmit,
  onInterrupt,
  onNeedsConfiguration,
}: ComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 176)}px`;
  }, [value]);

  /** 根据运行态发送新任务或请求中断当前 Turn。 */
  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (isRunning) {
      onInterrupt();
      return;
    }
    const message = value.trim();
    if (!message) {
      return;
    }
    if (isUnavailable) {
      return;
    }
    if (!isReady) {
      onNeedsConfiguration();
      return;
    }
    onSubmit(message);
    setValue("");
  }

  /** 使用 Enter 发送，保留 Shift+Enter 输入换行。 */
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className="composer__surface">
        <div className="composer__context" aria-label="任务上下文">
          <span title="当前项目">
            <Folder size={14} aria-hidden="true" />
            {projectName}
          </span>
          <span>
            <TerminalSquare size={14} aria-hidden="true" />
            Workspace
          </span>
        </div>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isRunning}
          rows={1}
          maxLength={20_000}
          placeholder="随心输入任务目标、约束和验收方式..."
          aria-label="任务输入"
        />
        <div className="composer__toolbar">
          <span className="model-label" title="当前模型">
            <span className="model-label__dot" aria-hidden="true" />
            {model}
          </span>
          <button
            className={`send-button${isRunning ? " is-running" : ""}`}
            type="submit"
            disabled={isUnavailable && !isRunning}
            aria-label={isRunning ? "中断任务" : "发送任务"}
            title={isRunning ? "中断任务" : "发送任务"}
          >
            {isRunning ? <Square size={15} fill="currentColor" /> : <ArrowUp size={19} />}
          </button>
        </div>
      </div>
      <p>模型结果可能存在错误，请核验重要改动与命令输出。</p>
    </form>
  );
}
