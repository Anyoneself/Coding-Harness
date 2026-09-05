import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({
  breaks: true,
  gfm: true,
});

/** 把模型返回的 Markdown 清洗为可安全插入页面的 HTML。 */
export function renderSafeMarkdown(content: string): string {
  const rendered = marked.parse(content, { async: false });
  return DOMPurify.sanitize(rendered, {
    USE_PROFILES: { html: true },
  });
}
