import { describe, expect, it } from "vitest";

import { renderSafeMarkdown } from "./markdown";

describe("模型 Markdown 渲染", () => {
  it("保留代码结构并移除脚本与事件处理器", () => {
    /** 验证模型文本不能通过 Markdown 向工作台注入可执行脚本。 */
    const html = renderSafeMarkdown(
      "```js\nconst ready = true;\n```\n<img src=x onerror=alert(1)><script>alert(2)</script>",
    );

    expect(html).toContain("<code");
    expect(html).not.toContain("<script");
    expect(html).not.toContain("onerror");
  });
});
