import { Eye, EyeOff, KeyRound, LoaderCircle } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";

interface ApiKeyDialogProps {
  isOpen: boolean;
  error: string;
  isSubmitting: boolean;
  onSubmit: (apiKey: string) => void;
}

/** 收集首次运行密钥，并确保值只存在于当前组件内存。 */
export function ApiKeyDialog({
  isOpen,
  error,
  isSubmitting,
  onSubmit,
}: ApiKeyDialogProps) {
  const [apiKey, setApiKey] = useState("");
  const [isVisible, setIsVisible] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    } else {
      setApiKey("");
      setIsVisible(false);
    }
  }, [isOpen]);

  /** 提交去除首尾空白后的密钥，不写入浏览器存储。 */
  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const secret = apiKey.trim();
    if (secret) {
      onSubmit(secret);
    }
  }

  if (!isOpen) {
    return null;
  }
  return (
    <div className="dialog-backdrop" role="presentation">
      <section
        className="api-key-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="api-key-title"
      >
        <div className="api-key-dialog__heading">
          <span aria-hidden="true">
            <KeyRound size={20} />
          </span>
          <div>
            <h2 id="api-key-title">连接 DeepSeek</h2>
            <p>
              API Key 仅写入本机 <code>.env</code>，不会保存在浏览器中。
            </p>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <label htmlFor="api-key-input">API Key</label>
          <div className="secret-field">
            <input
              ref={inputRef}
              id="api-key-input"
              type={isVisible ? "text" : "password"}
              value={apiKey}
              minLength={16}
              maxLength={256}
              pattern="sk-[A-Za-z0-9._-]+"
              autoComplete="off"
              spellCheck={false}
              disabled={isSubmitting}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="sk-..."
              required
            />
            <button
              type="button"
              onClick={() => setIsVisible((current) => !current)}
              aria-label={isVisible ? "隐藏 API Key" : "显示 API Key"}
              title={isVisible ? "隐藏 API Key" : "显示 API Key"}
            >
              {isVisible ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          <p className="form-error" role="status">
            {error}
          </p>
          <button className="primary-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <KeyRound size={17} />
            )}
            {isSubmitting ? "正在连接" : "保存并连接"}
          </button>
        </form>
      </section>
    </div>
  );
}
